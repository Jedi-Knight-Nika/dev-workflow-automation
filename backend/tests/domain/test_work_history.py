from app.agent_runtime.domain.work_history import public_work_plans


def test_work_history_excludes_instructions_and_accepts_only_bounded_acyclic_graphs():
    plans = [
        {
            "revision": 0,
            "objective": "private requirement",
            "units": [
                {
                    "id": "contract",
                    "status": "READY",
                    "depends_on": [],
                    "objective": "private code",
                },
                {"id": "implementation", "status": "RUNNING", "depends_on": [0]},
            ],
        }
    ]
    public = public_work_plans(plans)
    assert "private" not in str(public)
    assert public[0]["units"][1]["depends_on"] == [0]
    assert public_work_plans(plans + plans) == []
    plans[0]["units"][0]["depends_on"] = [1]
    assert public_work_plans(plans) == []
    assert public_work_plans({"units": []}) == []
