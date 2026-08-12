"""
region_program_contacts.py
----------------------------
Resolves the DMP interface's "FWS Region" and "FWS Program" selections into
mdEditor contact UUIDs, using an mdEditor contacts export (the
"Manage Contacts > Export" JSON file for the Region/Program organization
records).

This replaces the notebook's old hardcoded block:

    akfwsrow = pd.DataFrame(columns=['uuid','Role'])
    akfwsrow.loc[0] = ['821858df-5d0e-445a-b027-014f5ef68782','administrator']
    akfwsrow.loc[1] = ['821858df-5d0e-445a-b027-014f5ef68782','distributor']
    akfwsrow.loc[2] = ['821858df-5d0e-445a-b027-014f5ef68782','publisher']

...which always pointed at the Alaska Region org contact no matter what the
project actually was. Now that the interface asks which FWS Region and
FWS Program(s) a project belongs to, we look up the matching org contacts
instead.

Usage inside the notebook (replaces the old akfwsrow block in the
"final_contacts" cell):

    import region_program_contacts as rpc
    admrows = rpc.build_admin_rows(df, region_program_contacts_path)
    final_contacts = pd.concat([final_contacts, admrows]).reset_index(drop=True)
"""

import json
import pandas as pd

# ---------------------------------------------------------------------------
# Translation tables: the exact option text shown in DMP_Interface.html's
# "FWS Region" / "FWS Program" dropdowns -> the exact "name" field used in
# the mdEditor contacts export for that same organization.
#
# These don't match character-for-character (e.g. the interface says
# "Migratory Birds", the contact record says "Migratory Bird Management"),
# so this table is what bridges the two. If your organization's contact
# names change, update the right-hand side here to match.
# ---------------------------------------------------------------------------
REGION_CONTACT_NAME = {
    "1 – Pacific Region": "U.S. Fish and Wildlife Service, Pacific Region",
    "2 – Southwest Region": "U.S. Fish and Wildlife Service, Southwest Region",
    "3 – Midwest Region": "U.S. Fish and Wildlife Service, Midwest Region",
    "4 – Southeast Region": "U.S. Fish and Wildlife Service, Southeast Region",
    "5 – Northeast Region": "U.S Fish and Wildlife Service, Northeast Region",  # sic - no period after "U.S" in source data
    "6 – Mountain-Prairie Region": "U.S. Fish and Wildlife Service, Mountain Prairie Region",
    "7 – Alaska Region": "U.S. Fish and Wildlife Service, Alaska Region",
    "8 – Pacific Southwest Region": "U.S. Fish and Wildlife Service, Pacific Southwest Region",
}

PROGRAM_CONTACT_NAME = {
    "Ecological Services": "Ecological Services",
    "Fish and Aquatic Conservation": "Fisheries and Aquatic Conservation",
    "Migratory Birds": "Migratory Bird Management",
    "National Wildlife Refuge System": "National Wildlife Refuge System",
    "Office of Subsistence Management": "Office of Subsistence Management",
    "Science Applications": "Science Applications",
}


def load_contact_records(contacts_json_path):
    """
    Parse an mdEditor contacts export and return {contact name: {"uuid":..., "json":...}}.

    "json" here is the record re-serialized in the same shape final_contacts
    expects in its own 'json' column (matching what the notebook's
    existing_contacts['contact_json'] looks like) -- i.e. the *outer*
    mdEditor record {"id":..., "attributes":{"json": "<escaped inner json>"}, "type":...},
    JSON-dumped to a string. Carrying this directly means we don't depend on
    these same org contacts also happening to exist in whatever file
    `contact_folder` points at -- this file is self-sufficient.
    """
    with open(contacts_json_path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    records = {}
    for record in raw.get("data", []):
        try:
            inner = json.loads(record["attributes"]["json"])
        except (KeyError, ValueError, TypeError):
            continue
        name = inner.get("name")
        contact_id = inner.get("contactId")
        if name and contact_id:
            records[name] = {"uuid": contact_id, "json": json.dumps(record)}
    return records


def load_contact_name_to_uuid(contacts_json_path):
    """Convenience wrapper: {contact name: uuid} only (no json payload)."""
    return {name: rec["uuid"] for name, rec in load_contact_records(contacts_json_path).items()}


def build_admin_rows(df, contacts_json_path, include_region_distributor_publisher=True):
    """
    Build the dataframe of rows to append to `final_contacts`, assigning:
      - the project's FWS Region as 'administrator'
        (and, by default, also 'distributor' and 'publisher' -- the same
        three roles the old hardcoded Alaska Region contact used to cover)
      - each of the project's FWS Program(s) as 'administrator'

    `df` is the dataframe produced by dmp_json_to_dataframe.build_dataframe().
    Returns a DataFrame with columns ['uuid','Role','json'], ready to concat
    onto final_contacts. The 'json' column is pre-filled (from
    contacts_json_path itself) so the notebook doesn't try to generate a new
    stub contact record for these -- they already exist in mdEditor under a
    permanent uuid, so we want to reference them, not recreate them.

    Prints a warning (and skips that entry) if a selected region/program
    doesn't have a matching contact record, rather than failing silently.
    """
    records = load_contact_records(contacts_json_path)

    rows = []

    region_value = df.loc[df.field == "fwsRegion", "value"]
    region_value = region_value.values[0] if len(region_value) else ""
    if region_value:
        contact_name = REGION_CONTACT_NAME.get(region_value)
        record = records.get(contact_name) if contact_name else None
        if record:
            rows.append({"uuid": record["uuid"], "Role": "administrator", "json": record["json"]})
            if include_region_distributor_publisher:
                rows.append({"uuid": record["uuid"], "Role": "distributor", "json": record["json"]})
                rows.append({"uuid": record["uuid"], "Role": "publisher", "json": record["json"]})
        else:
            print(f"[region_program_contacts] WARNING: no contact match found for FWS Region {region_value!r} "
                  f"-- it will not be added as a contact on any metadata record.")

    program_values = df.loc[df.field.str.startswith("FWSProgram"), "value"].dropna().tolist()
    for program_value in program_values:
        if not program_value:
            continue
        contact_name = PROGRAM_CONTACT_NAME.get(program_value)
        record = records.get(contact_name) if contact_name else None
        if record:
            rows.append({"uuid": record["uuid"], "Role": "administrator", "json": record["json"]})
        else:
            print(f"[region_program_contacts] WARNING: no contact match found for FWS Program {program_value!r} "
                  f"-- it will not be added as a contact on any metadata record.")

    return pd.DataFrame(rows, columns=["uuid", "Role", "json"])


if __name__ == "__main__":
    import sys
    import dmp_json_to_dataframe as bridge

    dmp_json = sys.argv[1] if len(sys.argv) > 1 else "test_data.json"
    contacts_json = sys.argv[2] if len(sys.argv) > 2 else "FWSRegion_Program_Contacts_mdeditor-20260811-235138.json"

    out_df, _, _ = bridge.build_dataframe(dmp_json)
    admin_rows = build_admin_rows(out_df, contacts_json)
    print(admin_rows)
