"""Who can see whose leads."""
from core.db import users_df


def team_ids(user, active_only=False):
    """Admin: everyone. Manager: self + people reporting to them. Salesperson: self."""
    df = users_df()
    if active_only:
        df = df[df["active"]]
    me = int(user["id"])
    if user["role"] == "admin":
        ids = [int(i) for i in df["id"]]
    elif user["role"] == "manager":
        ids = [int(i) for i in df[df["manager_id"] == me]["id"]]
    else:
        ids = []
    if me not in ids:
        ids.append(me)
    return ids


def owner_options(user):
    """{id: name} of active people this user can give a lead to."""
    df = users_df()
    df = df[df["active"] & df["id"].isin(team_ids(user, active_only=True))]
    return dict(sorted(((int(r["id"]), r["name"]) for r in df.to_dict("records")),
                       key=lambda kv: kv[1].lower()))
