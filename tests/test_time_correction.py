"""サーバー時間 -> UTC 変換処理のテスト。

MT5 が返す `time` (秒) と `time_msc` (ミリ秒) はいずれもブローカーの
サーバー時間 (例: GMT+3) 基準であるため、双方に同一のオフセットを
適用しないと両者の間にタイムゾーン分のズレが生じてしまう。
"""

from mt5_bridge.mt5_handler import MT5Handler

# GMT+3 サーバー (例: HFM / ICMarkets) を想定したオフセット
OFFSET_GMT3_SEC = 3 * 3600


def _handler(use_utc: bool = True, offset_sec: int | None = OFFSET_GMT3_SEC) -> MT5Handler:
    """オフセットを固定した MT5Handler を生成する (MT5 端末への接続は不要)。"""
    handler = MT5Handler(use_utc=use_utc)
    handler._server_offset_sec = offset_sec
    return handler


def test_msc_correction_subtracts_offset_in_milliseconds() -> None:
    """ミリ秒タイムスタンプからオフセットがミリ秒スケールで差し引かれること。"""
    handler = _handler()
    # サーバー時間 2024-01-01 03:00:00.123 (GMT+3) = UTC 2024-01-01 00:00:00.123
    server_msc = 1_704_078_000_123
    assert handler._apply_time_correction_msc(server_msc) == 1_704_067_200_123


def test_sec_and_msc_stay_consistent() -> None:
    """補正後の `time` と `time_msc` が同一時刻を指すこと (本来の不具合の再現テスト)。"""
    handler = _handler()
    server_sec = 1_704_078_000
    server_msc = server_sec * 1000 + 456

    corrected_sec = handler._apply_time_correction(server_sec)
    corrected_msc = handler._apply_time_correction_msc(server_msc)

    # ミリ秒側を秒に落としたとき、秒側と一致していなければならない
    assert corrected_msc // 1000 == corrected_sec


def test_zero_msc_is_not_corrected() -> None:
    """`time_msc` が未設定 (0) のレコードは補正せず 0 のままとすること。"""
    handler = _handler()
    # 補正してしまうと負値になり、不正な日時として解釈されてしまう
    assert handler._apply_time_correction_msc(0) == 0


def test_no_utc_returns_raw_value() -> None:
    """use_utc=False の場合はサーバー時間のまま返すこと。"""
    handler = _handler(use_utc=False)
    assert handler._apply_time_correction_msc(1_704_078_000_123) == 1_704_078_000_123


def test_missing_offset_is_treated_as_zero() -> None:
    """オフセット未計算 (None) の場合は補正量 0 として扱うこと。"""
    handler = _handler(offset_sec=None)
    assert handler._apply_time_correction_msc(1_704_078_000_123) == 1_704_078_000_123


# --- サーバーオフセット推定の妥当性検証 ---------------------------------------


def test_plausible_offset_accepted_on_first_estimation() -> None:
    """初回推定でも現実的な範囲のオフセットは受理されること。"""
    handler = _handler(offset_sec=None)
    assert handler._is_plausible_offset(OFFSET_GMT3_SEC) is True
    assert handler._is_plausible_offset(-5 * 3600) is True


def test_out_of_range_offset_rejected() -> None:
    """実在しないタイムゾーン範囲のオフセットは棄却されること。"""
    handler = _handler(offset_sec=None)
    # 市場クローズ中に長時間経過すると、この種の非現実的な値が算出される
    assert handler._is_plausible_offset(-24 * 3600) is False
    assert handler._is_plausible_offset(20 * 3600) is False


def test_large_drift_from_known_offset_rejected() -> None:
    """確定済みオフセットから1時間を超えて乖離した推定値は棄却されること。"""
    handler = _handler()
    # 週末クローズ中に算出されがちな「-12時間」ケース (範囲内だが乖離が大きい)
    assert handler._is_plausible_offset(-12 * 3600) is False
    # 停止から2時間経過した時点での誤推定
    assert handler._is_plausible_offset(OFFSET_GMT3_SEC - 2 * 3600) is False


def test_dst_shift_within_one_hour_accepted() -> None:
    """夏時間切り替え相当 (±1時間) の変動は受理されること。"""
    handler = _handler()
    assert handler._is_plausible_offset(OFFSET_GMT3_SEC - 3600) is True
    assert handler._is_plausible_offset(OFFSET_GMT3_SEC + 3600) is True
