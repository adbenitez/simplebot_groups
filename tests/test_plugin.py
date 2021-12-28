class TestPlugin:
    def test_list(self, mocker) -> None:
        mocker.get_one_reply("/list")
