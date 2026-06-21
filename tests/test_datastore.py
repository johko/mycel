from mycel.demo.connector.datastore import DataStore


def test_list_records(node_config):
    store = DataStore(node_config.data_path)
    listed = store.list_records()
    assert {"id": "R1", "label": "record one"} in listed
    assert len(listed) == 2


def test_get_record(node_config):
    store = DataStore(node_config.data_path)
    assert store.get_record("R1")["value"] == 42


def test_get_missing_record(node_config):
    store = DataStore(node_config.data_path)
    assert "error" in store.get_record("NOPE")
