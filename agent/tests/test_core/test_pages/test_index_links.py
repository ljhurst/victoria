import boto3
import pytest
from moto import mock_aws

from victoria.core.pages import index_links
from victoria.core.storage import wiki

BUCKET = "victoria-test"
SEED_INDEX = "# Wiki index\n\n## House\n\n_(no pages yet — created by `remember` as topics come up)_\n\n## Business\n\n_(no pages yet — created by `remember` as topics come up)_\n"


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        wiki.put_file(BUCKET, "index.md", SEED_INDEX)
        yield client


class TestEnsureLinked:
    def test_appends_link_replacing_placeholder(self):
        result = index_links.ensure_linked(SEED_INDEX, "wiki/house/plants.md", "Plants")
        assert "[Plants](wiki/house/plants.md)" in result
        house_section = result.split("## House")[1].split("## Business")[0]
        assert "_(no pages yet" not in house_section

    def test_is_idempotent(self):
        once = index_links.ensure_linked(SEED_INDEX, "wiki/house/plants.md", "Plants")
        twice = index_links.ensure_linked(once, "wiki/house/plants.md", "Plants")
        assert once == twice
        assert once.count("plants.md") == 1

    def test_business_page_goes_under_business_heading(self):
        result = index_links.ensure_linked(SEED_INDEX, "wiki/business/hours.md", "Hours")
        business_section = result.split("## Business")[1]
        assert "[Hours](wiki/business/hours.md)" in business_section
        house_section = result.split("## House")[1].split("## Business")[0]
        assert "hours.md" not in house_section

    def test_new_domain_gets_its_own_heading(self):
        result = index_links.ensure_linked(SEED_INDEX, "wiki/home-office/desk.md", "Desk")
        assert result.endswith("## Home Office\n\n- [Desk](wiki/home-office/desk.md)\n")
        assert "desk.md" not in result.split("## Home Office")[0]

    def test_matches_existing_heading_regardless_of_wording(self):
        index_md = SEED_INDEX + "\n## Home Office\n\n- [Desk](wiki/home-office/desk.md)\n"
        result = index_links.ensure_linked(index_md, "wiki/home-office/chair.md", "Chair")
        assert result.count("## Home Office") == 1
        assert "- [Chair](wiki/home-office/chair.md)" in result.split("## Home Office")[1]


def test_domain_headings_are_read_from_index():
    assert list(index_links.domain_headings(SEED_INDEX)) == ["house", "business"]


def test_link_in_index_adds_the_link_once(s3_bucket):
    index_links.link_in_index(BUCKET, "index.md", "wiki/house/plants.md", "Plants")
    index_links.link_in_index(BUCKET, "index.md", "wiki/house/plants.md", "Plants")

    index = wiki.get_file(BUCKET, "index.md").content
    assert index.count("[Plants](wiki/house/plants.md)") == 1
    assert "_(no pages yet" not in index.split("## House")[1].split("## Business")[0]
