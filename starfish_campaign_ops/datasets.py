"""Named demo datasets.

Each dataset points at a folder of campaign files (input_data/, input_data2/,
...) and carries the roster + campaign metadata used by the loaders.  The
campaign name/ID are also re-read from `campaign_brief.xlsx` when available,
so the DB always reflects what is actually inside the folder.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from schemas.creator import Creator

BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Dataset:
    key: str            # folder name, e.g. "input_data"
    label: str          # human-friendly name for the UI
    campaign_id: str
    client_name: str
    campaign_name: str
    roster: tuple[Creator, ...]

    @property
    def directory(self) -> Path:
        return BASE_DIR / self.key


_RAMADAN_ROSTER = tuple([
    Creator(creator_id="ST-001", canonical_name="Sara Ahmed", instagram_handle="@sara.ahmed"),
    Creator(creator_id="ST-002", canonical_name="Omar Ali", instagram_handle="@omar.ali"),
    Creator(creator_id="ST-003", canonical_name="Lina Hassan", instagram_handle="@lina.hassan"),
    Creator(creator_id="ST-004", canonical_name="Youssef Karim", instagram_handle="@youssefk"),
    Creator(creator_id="ST-005", canonical_name="Nour El-Sayed", instagram_handle="@nour.elsayed"),
    Creator(creator_id="ST-006", canonical_name="Maya Farouk", instagram_handle="@maya.farouk"),
    Creator(creator_id="ST-007", canonical_name="Hana Mostafa", instagram_handle="@hana.mostafa"),
    Creator(creator_id="ST-008", canonical_name="Rana Khalil", instagram_handle="@rana.khalil"),
    Creator(creator_id="ST-009", canonical_name="Dina Fathy", instagram_handle="@dina.fathy"),
    Creator(creator_id="ST-010", canonical_name="Salma Adel", instagram_handle="@salma.adel"),
    Creator(creator_id="ST-011", canonical_name="Aya Rahman", instagram_handle="@aya.rahman"),
    Creator(creator_id="ST-012", canonical_name="Karim Nasser", instagram_handle="@karim.nasser"),
])

_SUMFIT_ROSTER = tuple([
    Creator(creator_id="ST-001", canonical_name="Menna Samir", instagram_handle="@menna.samir"),
    Creator(creator_id="ST-002", canonical_name="Tarek Yousef", instagram_handle="@tarek.yousef"),
    Creator(creator_id="ST-003", canonical_name="Freddie Morgan", instagram_handle="@freddie.m"),
    Creator(creator_id="ST-004", canonical_name="Peter Butros", instagram_handle="@peter.b"),
    Creator(creator_id="ST-005", canonical_name="Salah Abdalla", instagram_handle="@salah.abdalla"),
    Creator(creator_id="ST-006", canonical_name="Nina Boulos", instagram_handle="@nina.boulos"),
    Creator(creator_id="ST-007", canonical_name="Mario Nabeel", instagram_handle="@mario.nabeel"),
    Creator(creator_id="ST-008", canonical_name="Bassem Farid", instagram_handle="@bassem.farid"),
    Creator(creator_id="ST-009", canonical_name="Sandy Girgis", instagram_handle="@sandy.girgis"),
    Creator(creator_id="ST-010", canonical_name="Reem Helmy", instagram_handle="@reem.helmy"),
    Creator(creator_id="ST-011", canonical_name="Hany Soliman", instagram_handle="@hany.soliman"),
])

_RAMTECH_ROSTER = tuple([
    Creator(creator_id="ST-001", canonical_name="Karim Fahmy", instagram_handle="@karim.fahmy"),
    Creator(creator_id="ST-002", canonical_name="Youssef Adel", instagram_handle="@youssef.adel"),
    Creator(creator_id="ST-003", canonical_name="Laila Mansour", instagram_handle="@laila.m"),
    Creator(creator_id="ST-004", canonical_name="Hassan Ibrahim", instagram_handle="@hassan.ibrahim"),
    Creator(creator_id="ST-005", canonical_name="Salma Khaled", instagram_handle="@salma.khaled"),
    Creator(creator_id="ST-006", canonical_name="Nour Hamdy", instagram_handle="@nour.hamdy"),
    Creator(creator_id="ST-007", canonical_name="Yara Sameh", instagram_handle="@yara.sameh"),
    Creator(creator_id="ST-008", canonical_name="Ady Guergues", instagram_handle="@ady.guergues"),
    Creator(creator_id="ST-009", canonical_name="Mariam Faiez", instagram_handle="@mariam.faiez"),
    Creator(creator_id="ST-010", canonical_name="Dina Sherif", instagram_handle="@dina.sherif"),
    Creator(creator_id="ST-011", canonical_name="George Bakhoum", instagram_handle="@george.bakhoum"),
])

DATASETS: dict[str, Dataset] = {
    "input_data": Dataset(
        key="input_data",
        label="ABC Beauty — Ramadan Skincare Campaign",
        campaign_id="CMP-RAMADAN-26",
        client_name="ABC Beauty",
        campaign_name="Ramadan Skincare Campaign",
        roster=_RAMADAN_ROSTER,
    ),
    "input_data2": Dataset(
        key="input_data2",
        label="XYZ Fitness — Summer Fitness Campaign",
        campaign_id="CMP-SUMFIT-26",
        client_name="XYZ Fitness",
        campaign_name="Summer Fitness Campaign",
        roster=_SUMFIT_ROSTER,
    ),
    "input_data3": Dataset(
        key="input_data3",
        label="Nova Tech — Ramadan Tech Campaign",
        campaign_id="CMP-RAMTECH-26",
        client_name="Nova Tech",
        campaign_name="Ramadan Tech Campaign",
        roster=_RAMTECH_ROSTER,
    ),
}

DEFAULT_DATASET = "input_data2"


def get_dataset(key: str | None) -> Dataset:
    return DATASETS.get(key or DEFAULT_DATASET, DATASETS[DEFAULT_DATASET])


def brief_overrides(directory: Path) -> dict:
    """Read campaign_brief.xlsx (if present) so DB metadata matches the files."""
    out: dict = {}
    brief = directory / "campaign_brief.xlsx"
    if not brief.exists():
        return out
    try:
        import pandas as pd

        raw = pd.read_excel(brief, header=None)
        pairs = {str(r[0]).strip().lower(): str(r[1]).strip()
                 for _, r in raw.iterrows() if len(r) > 1 and pd.notna(r[0])}
        if pairs.get("campaign_id"):
            out["campaign_id"] = pairs["campaign_id"]
        if pairs.get("client_name"):
            out["client_name"] = pairs["client_name"]
        if pairs.get("campaign_name"):
            out["campaign_name"] = pairs["campaign_name"]
        if pairs.get("currency"):
            out["currency"] = pairs["currency"]
        if pairs.get("start_date"):
            out["start_date"] = pairs["start_date"][:10]
        if pairs.get("end_date"):
            out["end_date"] = pairs["end_date"][:10]
    except Exception:  # never let a bad brief block the load
        pass
    return out
