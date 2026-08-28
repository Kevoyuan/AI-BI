import pandas as pd

from modules.pospal_live_data import LivePospalData
from modules.privacy import sanitize_live_data


def test_sanitize_live_data_replaces_identifiers_but_preserves_metrics():
    live = LivePospalData(
        sales=pd.DataFrame(
            {
                "流水号": ["real-order-1", "real-order-1"],
                "会员卡号": ["13812345678", "13812345678"],
                "会员姓名": ["张三", "张三"],
                "实收金额": [10.0, 20.0],
            }
        ),
        loss=pd.DataFrame(),
        cards=pd.DataFrame(),
        cards_detail=pd.DataFrame(
            {
                "支付平台流水号": ["real-payment-1"],
                "会员手机号": ["13812345678"],
                "充值金额": [100.0],
            }
        ),
        sales_detail=pd.DataFrame(
            {"流水号": ["real-order-1"], "实收金额": [30.0]}
        ),
        payments=pd.DataFrame(),
    )

    safe = sanitize_live_data(live)
    assert safe.sales["流水号"].tolist() == ["TXN-0001", "TXN-0001"]
    assert safe.sales_detail["流水号"].tolist() == ["TXN-0001"]
    assert safe.sales["会员卡号"].iloc[0] == "CARD-0001"
    assert safe.sales["会员姓名"].iloc[0] == "MEMBER-0001"
    assert safe.cards_detail["支付平台流水号"].iloc[0] == "PAY-0001"
    assert safe.cards_detail["会员手机号"].iloc[0] == "PHONE-0001"
    assert safe.sales["实收金额"].tolist() == [10.0, 20.0]
    assert safe.cards_detail["充值金额"].iloc[0] == 100.0


def test_sanitize_live_data_is_idempotent_for_public_labels():
    live = LivePospalData(
        sales=pd.DataFrame({"流水号": ["TXN-0001"], "会员卡号": ["CARD-0001"]}),
        loss=pd.DataFrame(),
        cards=pd.DataFrame(),
        cards_detail=pd.DataFrame(),
        sales_detail=pd.DataFrame(),
        payments=pd.DataFrame(),
    )
    safe = sanitize_live_data(live)
    assert safe.sales.equals(live.sales)
