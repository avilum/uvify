import pytest
from fastapi.testclient import TestClient
from src.uvify import api

client = TestClient(api)

REPOS = [
    ("psf/requests", "https://github.com/psf/requests"),
    ("psf/black", "https://github.com/psf/black"),
    ("linqit", "https://github.com/avilum/linqit"),
    ("yalla", "https://github.com/avilum/yalla"),
    ("numpy", "https://github.com/numpy/numpy"),
    ("pandas", "https://github.com/pandas-dev/pandas"),
    ("matplotlib", "https://github.com/matplotlib/matplotlib"),
    ("scipy", "https://github.com/scipy/scipy"),
    ("scikit-learn", "https://github.com/scikit-learn/scikit-learn"),
    ("scikit-image", "https://github.com/scikit-image/scikit-image"),
    ("pytorch", "https://github.com/pytorch/pytorch"),
    ("tensorflow", "https://github.com/tensorflow/tensorflow"),
    ("keras", "https://github.com/keras-team/keras"),
    ("torchvision", "https://github.com/pytorch/vision"),
]


@pytest.mark.parametrize("repo_name,repo_url", REPOS)
def test_analyze_repo_with_avilum_repos(repo_name, repo_url):
    print(f"Testing {repo_name} with {repo_url}...")
    # input(f"Press Enter to continue...")
    response = client.get(f"/{repo_url}")
    assert response.status_code == 200
    data = response.json()
    print("DATA:", data)

    assert "oneLiner" in data[0]
    # assert "command" in data
    # assert "arguments" in data
    # assert data["command"] == "uv"
    # assert isinstance(data["arguments"], list)
    # assert any("with" in str(arg) for arg in data["arguments"])
