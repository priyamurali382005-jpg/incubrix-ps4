
from app import catalogue

HEADER = "name,url,platform_key,connector_key\n"


def test_valid_row_imports():
    report = catalogue.import_csv(
        HEADER
        + "Forum A,https://forum-a.com,discourse,discourse\n"
    )

    assert report["imported"] == 1
    assert report["invalid"] == 0


def test_duplicates_with_different_spelling_are_caught():
    csv_text = (
        HEADER
        + "Forum A,https://forum-a.com,discourse,discourse\n"
        + "Forum A again,http://www.FORUM-A.com/,discourse,discourse\n"
    )

    report = catalogue.import_csv(csv_text)

    assert report["imported"] == 1
    assert report["duplicates"] == 1


def test_same_url_different_platform_is_not_a_duplicate():
    csv_text = (
        HEADER
        + "Forum A,https://site.com,discourse,discourse\n"
        + "Blog A,https://site.com,ghost,ghost\n"
    )

    report = catalogue.import_csv(csv_text)

    assert report["imported"] == 2


def test_bad_rows_get_row_level_errors():
    csv_text = (
        HEADER
        + "No URL,not-a-url,discourse,discourse\n"
        + ",https://x.com,discourse,discourse\n"
        + "Odd,https://y.com,myspace,discourse\n"
    )

    report = catalogue.import_csv(csv_text)

    assert report["invalid"] == 3
    assert report["errors"][0]["row"] == 2
