import streamlit as st
import pandas as pd
import datetime
import numpy as np

# --- CONFIGURATION FIXE (PROTOCOLE T75) ---
SURFACE_T75 = 75 
DENSITE_MAX_HACAT = 133333 
CELLULES_CIBLE_80 = (SURFACE_T75 * DENSITE_MAX_HACAT) * 0.80 # 8,000,000 cellules
VOLUME_FALCON = 12.0 
TEMPS_ADHERENCE_H = 18.0 

# --- CONFIGURATION GOOGLE SHEETS ---
# ⚠️ REMPLACE CETTE URL PAR CELLE DE TON GOOGLE SHEETS CORRESPONDANT
URL_SHEET = "https://docs.google.com/spreadsheets/d/1uvB0Apu9GReQ79lWQmImtdcayQ55dwMq_0EfLpz6urE/edit?usp=sharing"

# Transformation de l'URL pour la lecture directe en CSV par Pandas
CSV_URL = URL_SHEET.replace("/edit?usp=sharing", "/export?format=csv")

def load_data_from_sheets():
    try:
        df = pd.read_csv(CSV_URL)
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        return df
    except Exception:
        # Si la feuille est vide ou inaccessible, on crée un DataFrame structurel
        return pd.DataFrame(columns=[
            "Date", "Passage_Numero", "Confluence_Visuelle", "Concentration_Mesuree", 
            "Cellules_Totales_Recoltees", "Cellules_Ensemencees", 
            "Jours_Attendus", "DT_Calcule"
        ])

def save_to_sheets(new_row_df):
    # Pour écrire de manière ultra-simple sans clés API Google complexes (qui nécessitent un compte cloud pro),
    # on va générer un lien de soumission ou utiliser les secrets de Streamlit.
    # Dans un premier temps, Streamlit offre un outil natif ultra-sécurisé appelé st.connection("gsheets")
    pass

# --- INITIALISATION ---
st.set_page_config(page_title="HaCaT T75 Cloud", layout="centered")
st.title("🧫 Hacat Passing Assistant")

# Connexion native Streamlit <-> Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df_logs = conn.read(spreadsheet=URL_SHEET)
    if not df_logs.empty and "Date" in df_logs.columns:
        df_logs["Date"] = pd.to_datetime(df_logs["Date"]).dt.date
except Exception:
    # Alternative de secours si la connexion gsheets n'est pas encore configurée dans Streamlit Cloud
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
    
    # Récupération automatique du dernier numéro de passage pour proposer le suivant
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
    # On calcule d'abord le numéro suggéré de manière propre
    passage_suggere = max(1, dernier_p_num + 1)
    
    # On l'injecte simplement dans l'application
    passage_actuel = st.number_input("Numéro du passage actuel (P)", min_value=1, value=passage_suggere, step=1)
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
    st.error("⚠️ Intervalle trop court pour permettre l'adhérence.")
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
        st.info(f"💡 **Conseil :** Passez le volume final à **{vol_final_ajuste:.1f} mL** pour tricher sur le ratio, ou centrifugez le culot cellulaire.")
    else:
        st.success(f"✅ **Ratio optimal ({ratio_cellulaire:.1f}%)**")

    c1, c2, c3 = st.columns(3)
    c1.metric("Volume de cellules", f"{vol_a_prelever_ml*1000:.0f} µL" if vol_a_prelever_ml < 1 else f"{vol_a_prelever_ml:.2f} mL")
    c2.metric("Milieu neuf", f"{vol_milieu_frais_ml:.2f} mL")
    c3.metric("Inoculum requis", f"{cellules_a_ensemencer:,.0f} cell")

    # --- ENREGISTREMENT DANS GOOGLE SHEETS ---
    st.write("---")
    if st.button(f"💾 Envoyer P{passage_actuel} vers Google Sheets"):
        
        cellules_totales_falcon = concentration * VOLUME_FALCON
        dt_effectif = np.nan
        
        if not df_logs.empty:
            # On trie par date pour être sûr d'avoir le dernier historique
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

        new_entry = pd.DataFrame([{
            "Date": datetime.date.today().strftime("%Y-%m-%d"),
            "Passage_Numero": int(passage_actuel),
            "Confluence_Visuelle": int(confluence_visuelle),
            "Concentration_Mesuree": float(concentration),
            "Cellules_Totales_Recoltees": float(cellules_totales_falcon),
            "Cellules_Ensemencees": float(cellules_a_ensemencer),
            "Jours_Attendus": int((prochain_passage_date - datetime.date.today()).days),
            "DT_Calcule": float(dt_effectif if not np.isnan(dt_effectif) else doubling_time_h)
        }])
        
        # Envoi au Google Sheets via la connexion Streamlit Cloud
        try:
            df_updated = pd.concat([df_logs, new_entry], ignore_index=True)
            conn.update(spreadsheet=URL_SHEET, data=df_updated)
            st.success(f"Passage P{passage_actuel} enregistré avec succès dans Google Sheets !")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur d'écriture. Avez-vous bien mis le lien en mode 'Éditeur' ? Détails : {e}")

# --- HISTORIQUE DEPUIS LE CLOUD ---
st.header("📜 Historique synchronisé (Google Sheets)")
if not df_logs.empty:
    st.dataframe(df_logs.tail(10))
else:
    st.info("Aucune donnée détectée dans le Google Sheets.")
