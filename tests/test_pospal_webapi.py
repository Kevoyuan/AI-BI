from pathlib import Path

import pandas as pd

from modules.pospal_webapi import PospalWebApiExporter


class _JsonResponse:
    def json(self):
        return {
            "successed": True,
            "json": {
                "payMethodCols": ["银豹付支付", "储值卡支付"],
                "list": [
                    {
                        "Date": "2026-08-08",
                        "totalTicketCount": "2",
                        "营业实收": "80.00",
                        "银豹付支付": {"amount": "80.00", "ticketRecord": 1},
                        "储值卡支付": {"amount": "20.00", "ticketRecord": 1},
                    }
                ],
            },
        }


def test_export_store_payment_summary_flattens_dynamic_methods(tmp_path, monkeypatch):
    exporter = PospalWebApiExporter(session=None, base_url="https://example.test", headers={})
    monkeypatch.setattr(exporter, "_post", lambda *args, **kwargs: _JsonResponse())
    target = Path(tmp_path) / "payments.xlsx"

    exporter.export_store_payment_summary(target, "2026-08-01", "2026-08-31", "1")
    frame = pd.read_excel(target)

    assert frame["支付方式"].tolist() == ["银豹付支付", "储值卡支付"]
    assert frame["金额"].sum() == 100
    assert frame["支付笔数"].sum() == 2
