"""Admin page: add, rename, remove and reorder dropdown options."""
import pandas as pd
import streamlit as st

from core.leads import leads_df
from core.lists import LISTS, get_lists, save_lists, rename_in_leads
from core.ui import flash


def _editor(values, key):
    df = pd.DataFrame({"Option": values})
    out = st.data_editor(
        df, key=key, num_rows="dynamic", hide_index=True, width="stretch",
        column_config={"Option": st.column_config.TextColumn("Option", required=True)})
    return df, out


def _changes(before, after):
    """Return (new list, renames {old: new}, removed [old]) from the editor.
    Rows that existed keep their index, so an edited cell = a rename."""
    renames, removed = {}, []
    for i, old in before["Option"].items():
        if i in after.index:
            new = str(after.at[i, "Option"] or "").strip()
            if new and new != old:
                renames[old] = new
            elif not new:
                removed.append(old)
        else:
            removed.append(old)
    seen, new_list = set(), []
    for v in after["Option"]:
        v = str(v or "").strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            new_list.append(v)
    return new_list, renames, removed


def render(user):
    st.title("⚙️ Dropdowns")
    st.caption("Change the choices people see in the forms. **Add** a row at the bottom of "
               "the table, **click a cell** to rename, or select a row and press "
               "**Delete** (🗑️) to remove it. Then press Save.")
    flash("dd_flash")
    data = get_lists()
    which = st.segmented_control("List", list(LISTS), format_func=lambda k: LISTS[k][0],
                                 default="products", key="dd_which") or "products"
    title, help_, column = LISTS[which]
    st.caption(help_)

    company = None
    if which == "products":
        company = st.selectbox("Company", data["companies"], key="dd_company")
        values = data["products"].get(company, [])
    else:
        values = data[which]

    nonce = st.session_state.setdefault("dd_nonce", 0)
    before, after = _editor(values, key=f"dd_{which}_{company}_{nonce}")

    c1, c2 = st.columns(2)
    move = c2.selectbox("Move an option to the top", [""] + values, key=f"dd_move_{which}_{company}",
                        help="Options show in this order in the forms.")
    if c1.button("💾 Save", type="primary", width="stretch"):
        new_list, renames, removed = _changes(before, after)
        if move and move in new_list:
            new_list.remove(move)
            new_list.insert(0, move)
        if which == "companies":
            if not new_list:
                st.error("Keep at least one company.")
                return
            used = set(leads_df()["company"])
            blocked = [c for c in removed if c in used]
            if blocked:
                st.error("Can't remove " + ", ".join(blocked) + " — it has leads. "
                         "Rename it instead, or move those leads to another company first.")
                return
        if which == "activity_kinds" and not new_list:
            st.error("Keep at least one follow-up type.")
            return

        for old, new in renames.items():
            rename_in_leads(column, old, new, company=company)
        if which == "products":
            data["products"][company] = new_list
        else:
            data[which] = new_list
        if which == "companies":
            for old, new in renames.items():
                data["products"][new] = data["products"].pop(old, [])
            for c in removed:
                data["products"].pop(c, None)
            for c in new_list:
                data["products"].setdefault(c, [])
        save_lists(data)
        st.session_state["dd_nonce"] = nonce + 1
        msg = f"{title} saved."
        if renames and column:
            msg += " Renamed options were also updated on existing leads."
        st.session_state["dd_flash"] = msg
        st.rerun()
    if which in ("sources", "lost_reasons", "products"):
        st.caption("Removing an option only hides it from the forms. Old leads keep what "
                   "was chosen.")
