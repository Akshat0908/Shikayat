import asyncio
import json
import pytest
from eval import run_heldout

def test_user_cases_and_labels_preserved():
    cases=json.loads((run_heldout.ROOT/'eval/heldout/cases.json').read_text())
    assert [case['case_id'] for case in cases]==[f'CC-{n:03}' for n in range(1,11)]
    assert cases[0]['ground_truth']['reply_type']=='acknowledgment'
    assert cases[5]['ground_truth']['e_commerce_rules_2020_apply'] is False
    assert cases[4]['ground_truth']['resolved'] is True

def test_heldout_runner_refuses_second_run(tmp_path,monkeypatch):
    path=tmp_path/'result.json';path.write_text('{}');monkeypatch.setattr(run_heldout,'DEST',path)
    with pytest.raises(RuntimeError,match='refusing a repeat'):
        asyncio.run(run_heldout.run())
