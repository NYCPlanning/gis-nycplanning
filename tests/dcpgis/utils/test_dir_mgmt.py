from dcpgis.utils.dir_mgmt import create_dir_with_subdirs


def test_create_dir_with_subdirs_creates_nested_directories(tmp_path):
    parent_dir = tmp_path / "parent"
    sub_dirs = [
        "top_level",
        "another_top_level",
        "third_top_level/nested/nested_again",
    ]

    create_dir_with_subdirs(parent_dir_path=parent_dir, sub_dirs=sub_dirs)

    assert (parent_dir / "top_level").is_dir()
    assert (parent_dir / "another_top_level").is_dir()
    assert (parent_dir / "third_top_level" / "nested" / "nested_again").is_dir()
