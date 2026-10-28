from liquidity import build


def test_readme_block_replaces_only_the_marked_section(tmp_path):
    data = {
        "as_of": "2026-08",
        "updated": "2026-10-28",
        "headline": "Headline.",
        "metrics": [
            {
                "label": "Term deposits, all banks",
                "value": 130.7,
                "unit": "CLP tn",
                "period": "2026-08",
                "previous": 130.3,
                "change": 0.003,
                "change_type": "relative",
            },
            {
                "label": "Cost of term deposits",
                "value": 0.077,
                "unit": "share",
                "period": "2023-10",
                "previous": 0.082,
                "change": -0.005,
                "change_type": "points",
            },
        ],
    }
    block = build.readme_block(data)
    assert "| Term deposits, all banks | CLP 130.7 tn | CLP 130.3 tn | +0.3% |  |" in block
    assert "| Cost of term deposits | 7.7% | 8.2% | -0.5 pp | latest is October 2023 |" in block
    readme = tmp_path / "README.md"
    readme.write_text("before\n<!-- latest:start -->\n<!-- latest:end -->\nafter\n")
    build.write_readme(readme, block)
    build.write_readme(readme, block)  # idempotent
    text = readme.read_text()
    assert text.count("Latest reading") == 1 and text.startswith("before") and text.endswith("after\n")
