import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import seaborn as sns
import io

def load_and_clean_file(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        df_raw = pd.read_csv(uploaded_file, header=None)
    else:
        df_raw = pd.read_excel(uploaded_file, header=None)

    # Drop all rows that are completely empty
    df_raw.dropna(how='all', inplace=True)

    # Find the first row with a minimum number of non-null entries to treat as header
    for i, row in df_raw.iterrows():
        if row.notnull().sum() >= 3:  
            df_raw.columns = row
            df_cleaned = df_raw.iloc[i+1:].reset_index(drop=True)

            # clean column names
            df_cleaned.columns = [str(col).strip() for col in df_cleaned.columns]
            return df_cleaned

    return None

def analyze_billing_data(df):
    


    st.subheader("1. Identifying Top Denied CPT Codes")

    # Assuming 'Payment' column indicates payment status (0 for denied, >0 for paid)
    # 'Balances' column represents the outstanding amount.
    # Using 'Denial Reason' column for more precision if it exists.
    if 'Payment Amount' not in df.columns and 'Balance' not in df.columns:
        st.error("Error: The uploaded file must contain 'Payment' and/or 'Balances' columns for denial analysis.")
        return None, None, None, []

    # Let's define "denied" as having a payment of 0 or a balance > 0
    # We'll prioritize 'Payment' == 0 for denial identification if both are present
    
    df['Is_Denied'] = 0

    if 'Denial Reason' in df.columns:
        df['Is_Denied'] = df['Denial Reason'].notna() & (df['Denial Reason'].astype(str).str.strip() != "")
    
    # Use Payment and Balance logic if Denial Reason not present or empty
    elif 'Payment Amount' in df.columns:
        df['Is_Denied'] = (df['Payment Amount'] == 0).astype(int)
    elif 'Balance' in df.columns:
        df['Is_Denied'] = (df['Balance'] > 0).astype(int)


    if 'CPT Code' not in df.columns:
        st.error("Error: The uploaded file must contain a 'CPT Code' column.")
        return None, None, None, []

    denied_cpts = df[df['Is_Denied'] == 1]

    if denied_cpts.empty:
        st.success("It appears there are no denied claims in the uploaded data based on the 'Payment' or 'Balances' columns.")
        return pd.DataFrame(), "No significant denials to analyze for root causes.", "No specific fixes needed based on current data.", []

    # Rank CPTs by frequency of denial
    top_denied_cpts = denied_cpts['CPT Code'].value_counts().reset_index()
    top_denied_cpts.columns = ['CPT Code', 'Denial Count']
    st.write("Top CPT Codes by Denial Count:")
    st.dataframe(top_denied_cpts)

    # Show denial rates per CPT
    cpt_denial_rates = df.groupby('CPT Code')['Is_Denied'].mean().reset_index()
    cpt_denial_rates.columns = ['CPT Code', 'Denial Rate']
    cpt_denial_rates = cpt_denial_rates.sort_values(by='Denial Rate', ascending=False)
    st.write("CPT Codes by Denial Rate:")
    st.dataframe(cpt_denial_rates)

    figures = []

    # Breakdown denials by payer (Insurance Company)
    if 'Insurance Company Name' in df.columns:
        st.subheader("Denials Breakdown by Payer")
        denials_by_payer = denied_cpts['Insurance Company Name'].value_counts().reset_index()
        denials_by_payer.columns = ['Payer', 'Denial Count']
        st.dataframe(denials_by_payer)

        fig_payer_denials, ax_payer_denials = plt.subplots(figsize=(10, 6))
        sns.barplot(x='Denial Count', y='Payer', data=denials_by_payer, ax=ax_payer_denials)
        ax_payer_denials.set_title('Denials by Insurance Company')
        ax_payer_denials.set_xlabel('Number of Denials')
        ax_payer_denials.set_ylabel('Insurance Company')
        plt.tight_layout()
        figures.append(fig_payer_denials)
        st.pyplot(fig_payer_denials)

    # Breakdown denials by provider (Physician Name)
    if 'Physician Name' in df.columns:
        st.subheader("Denials Breakdown by Provider")
        denials_by_provider = denied_cpts['Physician Name'].value_counts().reset_index()
        denials_by_provider.columns = ['Provider', 'Denial Count']
        st.dataframe(denials_by_provider)

        fig_provider_denials, ax_provider_denials = plt.subplots(figsize=(10, 6))
        sns.barplot(x='Denial Count', y='Provider', data=denials_by_provider, ax=ax_provider_denials)
        ax_provider_denials.set_title('Denials by Physician')
        ax_provider_denials.set_xlabel('Number of Denials')
        ax_provider_denials.set_ylabel('Physician Name')
        plt.tight_layout()
        figures.append(fig_provider_denials)
        st.pyplot(fig_provider_denials)

    st.subheader("2. Detecting Root Causes")
    root_causes_summary = "Based on the analysis of top denied CPTs and payer/provider trends, here are potential root causes:\n\n"

    # Common root causes based on typical RCM issues
    # These are generalizations and would be more specific with a 'Denial Reason' column
    potential_causes = {
        "Modifier issues": "Often, denials occur due to incorrect or missing modifiers for CPT codes, especially when performed with other procedures or under specific circumstances.",
        "LCD/NCD mismatch": "Local Coverage Determinations (LCDs) and National Coverage Determinations (NCDs) define medical necessity for certain services. Mismatches can lead to denials.",
        "Bundling edits (NCCI)": "National Correct Coding Initiative (NCCI) edits prevent unbundling of services. If two codes are bundled, billing them separately can lead to denial.",
        "Lack of documentation": "Insufficient or missing clinical documentation to support the services billed is a frequent cause of denials.",
        "Prior authorization problems": "Services requiring pre-approval from the insurance company, if not obtained or incorrectly obtained, will be denied.",
        "Credentialing or provider enrollment issues": "If the physician is not properly credentialed or enrolled with a specific payer, claims will be denied.",
        "Payer-specific policies": "Some payers have unique billing guidelines or medical policies that, if not followed, lead to denials."
    }

    # Example: If a specific CPT is denied across multiple payers, it might be a coding or documentation issue for that CPT.
    # If a specific payer is denying many CPTs, it might be a payer policy or credentialing issue.
    # We can infer some general root causes based on the aggregated data.

    if not top_denied_cpts.empty:
        root_causes_summary += f"- High denial counts for CPT codes like {', '.join(top_denied_cpts['CPT Code'].head(3).astype(str).tolist())} suggest potential issues with documentation, coding, or medical necessity for these specific procedures.  \n"

    if 'Insurance Company Name' in df.columns and not denials_by_payer.empty:
        top_denying_payers = denials_by_payer[denials_by_payer['Denial Count'] == denials_by_payer['Denial Count'].max()]['Payer'].tolist()
        if top_denying_payers:
            root_causes_summary += f"- Significant denials from payers like {', '.join(top_denying_payers)} could indicate payer-specific policy mismatches, prior authorization hurdles, or even provider credentialing issues with these entities.  \n"

    if 'Physician Name' in df.columns and not denials_by_provider.empty:
        top_denying_providers = denials_by_provider[denials_by_provider['Denial Count'] == denials_by_provider['Denial Count'].max()]['Provider'].tolist()
        if top_denying_providers:
            root_causes_summary += f"- If certain physicians ({', '.join(top_denying_providers)}) have a disproportionately high denial rate, it might point to consistent documentation gaps, incorrect coding practices, or issues with their specific service lines.  \n"

    root_causes_summary += "\nGeneral considerations that are common root causes for denials include: \n"
    for cause, description in potential_causes.items():
        root_causes_summary += f"- **{cause}**: {description}  \n"


    st.markdown(root_causes_summary)

    st.subheader("3. Recommending Fixes and Strategies")
    recommended_fixes = "Based on the identified root causes, here are recommended fixes and strategies:\n\n"


    recommended_fixes += "- **Documentation Improvements**: For frequently denied CPTs, review and enhance clinical documentation to ensure it fully supports the medical necessity of the services billed. Conduct audits of physician notes.  \n"
    recommended_fixes += "- **Coding Accuracy Review**: Implement regular audits of coding practices, focusing on correct modifier usage, NCCI edits, and payer-specific coding guidelines. Consider specialized training for coders on problematic CPTs.  \n"
    recommended_fixes += "- **Prior Authorization Workflow Enhancement**: Streamline the prior authorization process. Ensure all services requiring pre-approval are identified early and authorizations are obtained correctly and timely.  \n"
    recommended_fixes += "- **Payer-Specific Appeal Language and Process**: Develop tailored appeal templates and strategies for frequent deniers. Engage with specific payers to understand their denial patterns and resolve systematic issues.  \n"
    recommended_fixes += "- **Provider Credentialing and Enrollment Verification**: Regularly verify that all physicians are properly credentialed and enrolled with all participating insurance companies to avoid denials due to provider eligibility.  \n"
    recommended_fixes += "- **Front Desk and Workflow Changes**: Implement changes to the front desk or coding workflow to prevent similar issues from occurring. This could involve verifying insurance eligibility more thoroughly or confirming prior authorizations before service. \n"
    recommended_fixes += "- **Payer Education and Communication**: Identify opportunities for direct communication with payers to address systemic denial issues and clarify billing requirements.  \n"
    recommended_fixes += "- **Appeals and Corrected Claim Submissions**: Establish a robust process for timely appeals of denied claims and submission of corrected claims once the root cause is addressed.  \n"


    st.markdown(recommended_fixes)

    return top_denied_cpts, root_causes_summary, recommended_fixes, figures

# --- Streamlit User Interface ---
st.set_page_config(layout="wide", page_title="RCM Denial Analysis")

st.title("Medical Billing Denial Analysis and RCM Performance Review")
st.markdown("Upload your Excel/CSV file to identify top denied CPT codes, analyze potential root causes, and get recommendations for improving your revenue cycle management.")
st.markdown("Analyze columns like 'CPT Code', 'Insurance Company Name', 'Physician Name', 'Payment', and 'Balances' (or adjustments/zero payments) and 'Denial Reasons' if available.  ")

uploaded_file = st.file_uploader("Choose an Excel or CSV file", type=["xlsx", "csv"])

if uploaded_file is not None:
    st.success("File successfully uploaded! Processing data...")

    try:
        df = load_and_clean_file(uploaded_file)

        if df is None:
            st.error("Unable to detect a valid header row. Please check the uploaded file.")
        else:
            st.write(" Detected Columns:", df.columns.tolist())
            st.subheader(" Uploaded Data Preview:")
            st.dataframe(df.head())

            # Continue with analysis
            top_denied_cpts, root_causes_summary, recommended_fixes, figures = analyze_billing_data(df)

            if top_denied_cpts is not None:
                 st.subheader("Summary of Analysis:")
                 st.markdown("Trends summarized, root causes diagnosed, and corrective actions recommended to reduce denials and improve collections.")

    except Exception as e:
        st.error(f"Error processing file: {e}. Please make sure the file format and contents are valid.")
        st.info("Expected columns include: 'CPT Code', 'Insurance Company Name', 'Physician Name', 'Payment', 'Balances', and optionally 'Denial Reason'.")

        

        