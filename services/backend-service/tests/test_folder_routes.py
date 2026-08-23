"""The folder routers for tracks, streams and podcasts share one implementation.

They used to be three near-identical files; the tests here run the same
expectations against all three, which is the point of having one factory.
"""

from __future__ import annotations

import pytest

# (URL prefix, payload for creating an item in such a folder)
MEDIA = [
    ("tracks", {"title": "A track", "source_type": "file", "source_uri": "/x/a.mp3"}),
    ("streams", {"title": "A stream", "source_uri": "http://example.invalid/s"}),
    ("podcasts", {"title": "A podcast", "rss_url": "http://example.invalid/f.xml"}),
]


@pytest.mark.parametrize(("kind", "item"), MEDIA)
def test_folder_crud_roundtrip(client, kind, item):
    created = client.post(f"/api/v1/{kind}/folders", json={"name": "Hoerspiele"})
    assert created.status_code == 201, created.text
    folder_id = created.json()["id"]

    assert [f["name"] for f in client.get(f"/api/v1/{kind}/folders").json()] == ["Hoerspiele"]
    assert client.get(f"/api/v1/{kind}/folders/{folder_id}").json()["name"] == "Hoerspiele"

    renamed = client.put(f"/api/v1/{kind}/folders/{folder_id}", json={"name": "Musik"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Musik"

    assert client.delete(f"/api/v1/{kind}/folders/{folder_id}").status_code == 204
    assert client.get(f"/api/v1/{kind}/folders/{folder_id}").status_code == 404


@pytest.mark.parametrize(("kind", "item"), MEDIA)
def test_unknown_folder_is_a_404(client, kind, item):
    response = client.get(f"/api/v1/{kind}/folders/424242")
    assert response.status_code == 404
    assert response.json()["code"] == "folder_not_found"


@pytest.mark.parametrize(("kind", "item"), MEDIA)
def test_a_folder_cannot_be_its_own_parent(client, kind, item):
    folder_id = client.post(f"/api/v1/{kind}/folders", json={"name": "Loop"}).json()["id"]
    response = client.put(f"/api/v1/{kind}/folders/{folder_id}", json={"parent_id": folder_id})
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_parent"


@pytest.mark.parametrize(("kind", "item"), MEDIA)
def test_deleting_a_folder_keeps_its_contents(client, kind, item):
    """Nothing a parent put in the library disappears with a folder."""
    folder_id = client.post(f"/api/v1/{kind}/folders", json={"name": "Box"}).json()["id"]
    child_id = client.post(
        f"/api/v1/{kind}/folders", json={"name": "Sub", "parent_id": folder_id}
    ).json()["id"]

    created = client.post(f"/api/v1/{kind}", json={**item, "folder_id": folder_id})
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]

    assert client.delete(f"/api/v1/{kind}/folders/{folder_id}").status_code == 204

    # The item survives and sits at the root now.
    assert client.get(f"/api/v1/{kind}/{item_id}").json()["folder_id"] is None
    # So does the child folder.
    assert client.get(f"/api/v1/{kind}/folders/{child_id}").json()["parent_id"] is None


@pytest.mark.parametrize(("kind", "item"), MEDIA)
def test_creating_below_an_unknown_parent_is_refused(client, kind, item):
    response = client.post(
        f"/api/v1/{kind}/folders", json={"name": "Orphan", "parent_id": 999999}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "folder_not_found"
