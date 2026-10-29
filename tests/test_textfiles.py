import io
import zipfile

import pytest

from liquidity import accounts, data, textfiles

HTML = (
    '<a href="articles-102413_recurso_1.zip?ts=1" class="card-img" aria-label="Descargar Noviembre 2025 (zip, se abre">'
    '<a href="articles-72974_recurso_1.zip?ts=2" class="card-img" aria-label="Descargar julio 2023 (zip, se abre">'
)


def _zip(name: str, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, text.encode("latin-1"))
    return buf.getvalue()


def test_index_maps_months_to_zip_urls():
    idx = textfiles.index(HTML)
    assert idx["2025-11"].endswith("articles-102413_recurso_1.zip")
    assert idx["2023-07"].startswith(textfiles.BASE)


@pytest.mark.parametrize(
    "amount, expected",
    [("-0798472059599,00", 798.472059599), ("-00580606880971", 580.606880971)],  # both number formats
)
def test_statement_rows_feed_the_same_extraction(amount, expected):
    z = _zip("202307/r1202307001.txt", f"001\tBANCO DE CHILE\n412180000\t{amount}\n416180000\t-0000000000000,00\n")
    rows = textfiles.statement(z, "2023-07", "001")
    assert accounts.extract_income(rows, 2023, 7)["term_expense"] == pytest.approx(expected)


def test_download_uses_the_fallback_when_the_api_fails(tmp_path):
    class Api:
        def institutions(self, y, m, kind="balances"):
            return {"001": "A", "999": "SYSTEM"}

        def results(self, y, m, code):
            raise RuntimeError("500")

    def fallback(period, code):
        if code == "999":
            raise KeyError(code)
        return [{"CodigoCuenta": "412180000", "MonedaTotal": "-1000000000,00"}]

    path = tmp_path / "inc.csv"
    got = data.download(path, Api(), (2023, 7), (2023, 7), log=lambda *_: None, kind="resultados", fallback=fallback)
    assert got == ["2023-07"]
    assert set(data.read(path)["code"]) == {"001"}
    assert (tmp_path / "inc_gaps.csv").read_text().split() == ["period"]  # a missing aggregate is not a gap
