import asyncio
import json
import pytest
from eval import run_heldout_v2

def test_v2_input_preserves_user_labels():
    cases=json.loads((run_heldout_v2.ROOT/'eval/heldout_v2/cases.json').read_text())
    assert len(cases)==10 and cases[-1]['reply_type']=='ambiguous'
    assert cases[6]['sector']=='Health Insurance' and cases[6]['ecommerce_rules_apply'] is False

def test_v2_refuses_second_run(tmp_path,monkeypatch):
    path=tmp_path/'result.json';path.write_text('{}');monkeypatch.setattr(run_heldout_v2,'DEST',path)
    with pytest.raises(RuntimeError,match='refusing a repeat'):
        asyncio.run(run_heldout_v2.run())
