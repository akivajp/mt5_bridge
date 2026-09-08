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
