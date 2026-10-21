import pandas as pd
import pytest

from liquidity import accounts, checks, data


def test_number_and_units_by_chart():
    assert accounts.number("51847187713806,00") == pytest.approx(51847187713806.0)
    assert accounts.number("41.194,55") == pytest.approx(41194.55)
    old = [{"CodigoCuenta": "2100000", "MonedaTotal": "18542791,00"}]  # CLP million
    new = [{"CodigoCuenta": "241000000", "MonedaTotal": "17069723639033,00"}]  # CLP
    assert accounts.extract(old, 2021, 12)["demand_deposits"] == pytest.approx(18542.791)
    assert accounts.extract(new, 2022, 1)["demand_deposits"] == pytest.approx(17069.723639033)


def _bal(rows):
    return pd.DataFrame(rows, columns=["period", "code", "name", "item", "clp_bn"])


def test_merger_is_detected_and_folded_into_the_acquirer():
    rows = []
    for p, a, b in [("2016-02", 100.0, 40.0), ("2016-03", 102.0, 41.0), ("2016-04", 145.0, None)]:
        rows.append((p, "039", "ITAU", "total_assets", a))
        rows.append((p, "039", "ITAU", "demand_deposits", a / 2))
        if b is not None:
            rows.append((p, "027", "CORPBANCA", "total_assets", b))
            rows.append((p, "027", "CORPBANCA", "demand_deposits", b / 2))
    bal = _bal(rows)
    m = checks.mergers(bal)
    assert list(m["code"]) == ["027"] and m["absorbed_by"].iloc[0] == "039"
    pf = checks.wide(checks.pro_forma(bal, m), "total_assets")
    assert list(pf["039"]) == [140.0, 143.0, 145.0]  # no artificial jump at the merger


def test_download_skips_months_already_there(tmp_path):
    class FakeApi:
        calls = 0

        def institutions(self, y, m):
            if (y, m) > (2008, 2):
                raise ValueError("not published")
            return {"001": "BANCO DE CHILE"}

        def balance(self, y, m, code):
            FakeApi.calls += 1
            return [{"CodigoCuenta": "2100000", "MonedaTotal": "1000,00"}]

    path = tmp_path / "b.csv"
    assert data.download(path, FakeApi(), (2008, 1), (2008, 3), log=lambda *_: None) == ["2008-01", "2008-02"]
    assert data.download(path, FakeApi(), (2008, 1), (2008, 3), log=lambda *_: None) == []
    assert FakeApi.calls == 2
    assert data.read(path).query("item == 'demand_deposits'")["clp_bn"].tolist() == [1.0, 1.0]


def test_institution_fields_vary_by_year():
    from liquidity.cmf import CmfApi

    api = CmfApi(key="k")
    api._get = lambda path: [{"CodigoInstitucion": "001", "NombreBanco": "BANCO DE CHILE "}]
    assert api.institutions(2008, 1) == {"001": "BANCO DE CHILE"}
