"""Real bio entries from City Tech directories (Oct 2026) that the reader must handle."""
from talentpool.sources import parse_citation, good_title


def title(t):
    return parse_citation(t, [])


def test_titles_found_after_author_lists():
    assert title("Hatzi K, Jiang Y, Huang C, Gearhart MD. (2013) A hybrid mechanism of action for BCL6 in B cells. "
                 "Cell Reports.")["title"] == "A hybrid mechanism of action for BCL6 in B cells"
    assert title("C. Calinescu, M. Penn and C. Sadowski, Presentations of principal subspaces of higher level "
                 "standard modules, 2018.")["title"].startswith("Presentations of principal subspaces")
    assert title("[35] Sahbani, S., Benabdallah, S. (2022) Assessment of coastal lagoon water quality. Water 14.")[
        "title"] == "Assessment of coastal lagoon water quality"


def test_quoted_titles_and_years():
    c = title('Lili Ma and Benito Mendoza (2022). "Assessing Student Outcomes Related to Design for ETAC-ABET '
              'Accreditation." Journal of Computing Sciences in Colleges. DOI: 10.5555/3580523.3580538')
    assert c["title"].startswith("Assessing Student Outcomes") and c["year"] == "2022"
    assert c["doi"] == "10.5555/3580523.3580538"


def test_junk_is_not_a_title():
    for junk in ["47-79", "051703", "3--21", "(Spring 2019)", "[ abstract and link ] , [ arXiv:1201-6636v1 ]",
                 "Panelists: Jessica Chen, Milica Zgaljic-Ramirez", "and Davos-Platz, Switzerland"]:
        assert not good_title(junk), junk


def test_unreadable_entries_are_flagged_not_guessed():
    assert title("Panelists: Jessica Chen, Milica Zgaljic-Ramirez, Danielle Ofri, Editor (BLR)")["clean"] is False


def test_amounts_and_roles():
    c = title('NSF ATE grant, Co-PI, "Building pathways in robotics technology" (2022-2025), $599,999')
    assert c["amount"] == 599999 and c["role"] == "Co-PI"
    assert title("Award of $, see below for details of the grant program in 2020")["amount"] == ""
