from query_doctor.impala import metadata_digest, table_metadata_facts


def test_metadata_digest_exposes_table_metadata_contract():
    assert metadata_digest.TABLE_METADATA_CONTEXT_HEADING == "## Table Metadata Context"
    assert table_metadata_facts.STATEMENTS == (
        "SHOW CREATE TABLE",
        "SHOW TABLE STATS",
        "SHOW COLUMN STATS",
    )
