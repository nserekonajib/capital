import pandas as pd

# ------------------------------
# 1. Load the student data
# ------------------------------
students_data = pd.read_excel("students.xlsx")  # file with Email, Phone, First Name, Last Name, Item Name

# ------------------------------
# 2. Load the CPA Level mapping
# ------------------------------
cpa_mapping = pd.read_excel("cpa_mapping.xlsx")  # file with Title, CPA LEVEL

# ------------------------------
# 3. Clean Phone numbers
# ------------------------------
def clean_phone(phone):
    if pd.isna(phone):
        return ""
    return str(phone).split("/")[0].strip()  # keep only first number if multiple

students_data["Phone"] = students_data["Phone (Billing)"].apply(clean_phone)

# ------------------------------
# 4. Create Full Name
# ------------------------------
students_data["Full Name"] = students_data["First Name (Shipping)"].astype(str).str.strip() + " " + \
                             students_data["Last Name (Shipping)"].astype(str).str.strip()

# ------------------------------
# 5. Merge with CPA mapping
# ------------------------------
final = students_data.merge(
    cpa_mapping,
    left_on="Item Name",
    right_on="Title",
    how="left"
)

# ------------------------------
# 6. Keep only required columns
# ------------------------------
final["Status"] = "Active"
final_export = final[["Full Name", "CPA LEVEL", "Email (Billing)", "Phone", "Status"]]

# Rename columns cleanly
final_export.columns = ["Full Name", "CPA Level", "Email", "Phone", "Status"]

# ------------------------------
# 7. Remove duplicate students (based on Email)
# ------------------------------
final_export = final_export.drop_duplicates(subset=["Email"], keep="first")

# ------------------------------
# 8. Save to Excel
# ------------------------------
final_export.to_excel("final_users_deduplicated.xlsx", index=False)

print("✅ Final Excel generated successfully: final_users_deduplicated.xlsx")
