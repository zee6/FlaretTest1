from football1.schema import AvailabilityClass, classify_column


def test_current_xg_is_post_match_not_pre_match_feature():
    assert classify_column("HxG") is AvailabilityClass.POST_MATCH
    assert classify_column("AxG") is AvailabilityClass.POST_MATCH


def test_closing_total_goals_and_asian_handicap_fields_are_market_data():
    for column in ("PC>2.5", "PC<2.5", "PCAHH", "PCAHA", "AHCh"):
        assert classify_column(column) is AvailabilityClass.MARKET
