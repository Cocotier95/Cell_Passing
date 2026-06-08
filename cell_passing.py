import streamlit as st
import pandas as pd
import datetime
import numpy as np
import requests

# --- CONFIGURATION FIXE (PROTOCOLE T75) ---
SURFACE_T75 = 75 
DENSITE_MAX_HACAT = 133333 
CELLULES_CIBLE_80 = (SURFACE_T75 * DENSITE_MAX_HACAT) * 0.80 
VOLUME_FALCON = 12.0 
TEMPS_ADHERENCE_H = 18.0

# --- CONFIGURATION LIENS GOOGLE ---
# 1. Mets ici ton lien Google Sheets en mode "Tous les utilisateurs disposant du lien : TÉLÉSPECTATEUR"
URL_SHEET = "https://docs.google.com/spreadsheets/d/1uvB0Apu9GReQ79lWQmImtdcayQ55dwMq_0EfLpz6urE/edit?usp=sharing"

# 2. Base de l'URL de ton Google Forms (s'arrête juste avant /viewform...)
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSfThAWozhMyfeYS6zKZUWyNB54hm9rQcsi7qmVXuZL1rMeXew/formResponse"

# 3. Remplace les chiffres ci-dessous par les numéros "entry.XXXXX" trouvés dans ton lien pré-rempli
FORM_ENTRIES = {
    "Date": "entry.111",
    "Passage_Numero": "entry.2222",
    "Confluence_Visuelle": "entry.333",
    "Concentration_Mesuree": "entry.444",
    "Cellules_Totales_Recoltees": "entry.555",
    "Cellules_Ensemencees": "entry.666",
    "Jours_Attendus": "entry.777",
    "DT_Calcule": "entry.888"
}
# --- LECTURE SÉCURISÉE ---
CSV_URL = URL_SHEET.replace("/edit?usp=sharing", "/export?format=csv")

def load_data_from_sheets():
    try:
        df = pd.read_csv(CSV_URL)
        if not df.empty and "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"]).dt.date
        return df
    except Exception:
        return pd.DataFrame(columns=["Date", "Passage_Numero", "Confluence_Visuelle", "Concentration_Mesuree", "Cellules_Totales_Recoltees", "Cellules_Ensemencees", "Jours_Attendus", "DT_Calcule"])

# --- INITIALISATION DE L'APP ---
st.set_page_config(page_title="HaCaT T75 Cloud", layout="centered")
st.title("🧫 Assistant HaCaT T75 & Google Sheets")

df_logs = load_data_from_sheets()

# --- APPRENTISSAGE ---
doubling_time_h = 26.0 
dernier_p_num = 0

if not df_logs.empty:
    if "DT_Calcule" in df_logs.columns:
        valid_dt = pd.to_numeric(df_logs["DT_Calcule"], errors='coerce').dropna()
        valid_dt = valid_dt[valid_dt > 10]
        if not valid_dt.empty:
            doubling_time_h = valid_dt.mean()
    
    if "Passage_Numero" in df_logs.columns:
        try:
            dernier_p_num = int(pd.to_numeric(df_logs["Passage_Numero"]).max())
        except:
            dernier_p_num = 0

st.sidebar.markdown(f"### 🧬 Profil des HaCaT\n"
                    f"* **Temps de doublement moyen :** `{doubling_time_h:.1f} heures`  \n"
                    f"* **Dernier passage enregistré :** `P{dernier_p_num}`")

# --- INTERFACE UTILISATEUR ---
st.header("1. Données du passage actuel")
col_p1, col_p2 = st.columns(2)
with col_p1:
    passage_suggere = max(1, dernier_p_num + 1)
    passage_actuel = st.number_input("Numéro du passage actuel (P)", min_value=1, value=int(passage_suggere), step=1)
    confluence_visuelle = st.slider("Confluence visuelle (%)", 10, 100, 80, 5)
with col_p2:
    concentration = st.number_input("Concentration (cellules/mL)", min_value=0, value=1200000, step=50000)

st.header("2. Planification du prochain passage")
col_p3, col_p4 = st.columns(2)
with col_p3:
    vol_final = st.number_input("Volume final de la T75 (mL)", min_value=5, max_value=20, value=12)
with col_p4:
    prochain_passage_date = st.date_input("Date du prochain passage", datetime.date.today() + datetime.timedelta(days=3))

# --- CALCULS ---
heures_totales = (prochain_passage_date - datetime.date.today()).days * 24
heures_proliferation_effective = heures_totales - TEMPS_ADHERENCE_H

if heures_proliferation_effective <= 0:
    st.error("⚠️ L'intervalle de temps choisi est trop court.")
else:
    nb_cycles_division = heures_proliferation_effective / doubling_time_h
    cellules_a_ensemencer = CELLULES_CIBLE_80 / (2 ** nb_cycles_division)
    
    vol_a_prelever_ml = cellules_a_ensemencer / concentration
    vol_milieu_frais_ml = vol_final - vol_a_prelever_ml
    ratio_cellulaire = (vol_a_prelever_ml / vol_final) * 100

    # --- RECOMMANDATIONS ---
    st.write("---")
    st.header(f"📋 Recette pour le passage P{passage_actuel}")
    
    if ratio_cellulaire < 10.0:
        st.error(f"🚨 **Attention : Ratio sous les 10% ({ratio_cellulaire:.1f}%)**")
        vol_final_ajuste = vol_a_prelever_ml / 0.10
        st.info(f"💡 **Conseil :** Passez le volume final à **{vol_final_ajuste:.1f} mL**.")
    else:
        st.success(f"✅ **Ratio optimal ({ratio_cellulaire:.1f}%)**")

    c1, c2, c3 = st.columns(3)
    c1.metric("Volume de cellules", f"{vol_a_prelever_ml*1000:.0f} µL" if vol_a_prelever_ml < 1 else f"{vol_a_prelever_ml:.2f} mL")
    c2.metric("Milieu neuf", f"{vol_milieu_frais_ml:.2f} mL")
    c3.metric("Inoculum requis", f"{cellules_a_ensemencer:,.0f} cell")

    # --- ENVOI VIA GOOGLE FORMS ---
    st.write("---")
    if st.button(f"💾 Envoyer P{passage_actuel} vers Google Sheets"):
        cellules_totales_falcon = concentration * VOLUME_FALCON
        dt_effectif = np.nan
        
        if not df_logs.empty:
            df_tri = df_logs.sort_values(by="Date")
            dernier_passage = df_tri.iloc[-1]
            try:
                cellules_initiales_prec = float(dernier_passage["Cellules_Ensemencees"])
                date_dernier = pd.to_datetime(dernier_passage["Date"]).date()
                jours_ecoules = (datetime.date.today() - date_dernier).days
                
                if jours_ecoules > 0 and cellules_totales_falcon > cellules_initiales_prec:
                    heures_ecoulees_totale = jours_ecoules * 24
                    heures_div_reelle = heures_ecoulees_totale - TEMPS_ADHERENCE_H
                    if heures_div_reelle > 0:
                        dt_effectif = (heures_div_reelle * np.log(2)) / (np.log(cellules_totales_falcon) - np.log(cellules_initiales_prec))
            except:
                pass

        # Préparation du dictionnaire pour le formulaire Google
        form_data = {
            FORM_ENTRIES["Date"]: datetime.date.today().strftime("%Y-%m-%d"),
            FORM_ENTRIES["Passage_Numero"]: int(passage_actuel),
            FORM_ENTRIES["Confluence_Visuelle"]: int(confluence_visuelle),
            FORM_ENTRIES["Concentration_Mesuree"]: float(concentration),
            FORM_ENTRIES["Cellules_Totales_Recoltees"]: float(cellules_totales_falcon),
            FORM_ENTRIES["Cellules_Ensemencees"]: float(cellules_a_ensemencer),
            FORM_ENTRIES["Jours_Attendus"]: int((prochain_passage_date - datetime.date.today()).days),
            FORM_ENTRIES["DT_Calcule"]: float(dt_effectif if not np.isnan(dt_effectif) else doubling_time_h)
        }
        
        try:
            # Envoi direct par requête HTTP POST (invisible et instantané)
            response = requests.post(FORM_URL, data=form_data)
            
            # C'EST ICI QUE LA CORRECTION A ÉTÉ APPORTÉE :
            if response.status_code == 200:
                st.success(f"Passage P{passage_actuel} envoyé au Cloud !")
                st.rerun()
            else:
                st.error("Une erreur est survenue lors de l'envoi.")
        except Exception as e:
            st.error(f"Erreur d'envoi : {e}")

# --- HISTORIQUE ---
st.header("📜 Historique synchronisé")
if not df_logs.empty:
    st.dataframe(df_logs.tail(10))
else:
    st.info("Aucune donnée enregistrée pour le moment.")
