import streamlit as st
import pandas as pd
import datetime
import os
import numpy as np

# --- CONFIGURATION FIXE (PROTOCOLE T75) ---
LOG_FILE = "log_passages_hacat_t75.csv"
SURFACE_T75 = 75 # cm²
DENSITE_MAX_HACAT = 133333 # cellules/cm² pour arriver à ~10M de cellules à 100% confluence
CELLULES_CIBLE_80 = (SURFACE_T75 * DENSITE_MAX_HACAT) * 0.80 # Soit exactement 8,000,000 cellules
VOLUME_FALCON = 12.0 # mL (1.5mL trypsine + 10.5mL DMEM)
TEMPS_ADHERENCE_H = 18.0 # Phase de latence (heures) avant le début de la division

def load_data():
    if os.path.exists(LOG_FILE):
        df = pd.read_csv(LOG_FILE)
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        return df
    return pd.DataFrame(columns=[
        "Date", "Confluence_Visuelle", "Concentration_Mesuree", 
        "Cellules_Totales_Recoltees", "Cellules_Ensemencees", 
        "Jours_Attendus", "DT_Calcule"
    ])

def save_data(df):
    df.to_csv(LOG_FILE, index=False)

# --- INITIALISATION ---
st.set_page_config(page_title="HaCaT T75 Protocol", layout="centered")
st.title("🧫 Assistant de Passage HaCaT (Spécial T75)")

df_logs = load_data()

# --- APPRENTISSAGE DU TEMPS DE DOUBLEMENT REEL ---
# Valeur standard de la littérature pour HaCaT en phase exponentielle : ~26 heures
doubling_time_h = 26.0 

if not df_logs.empty:
    valid_dt = df_logs["DT_Calcule"].dropna()
    valid_dt = valid_dt[valid_dt > 10] # Sécurité contre les valeurs aberrantes
    if not valid_dt.empty:
        doubling_time_h = valid_dt.mean()

st.sidebar.markdown(f"### 🧬 Constantes biologiques calculées\n"
                    f"* **Temps de doublement moyen :** `{doubling_time_h:.1f} heures`  \n"
                    f"* **Temps de latence (adhérence) :** `{TEMPS_ADHERENCE_H:.0f} heures`  \n\n"
                    f"*(Ces valeurs s'affinent automatiquement à chaque enregistrement)*")

# --- INTERFACE UTILISATEUR ---
st.header("1. Données de la récolte (Falcon 12 mL)")

col1, col2 = st.columns(2)
with col1:
    confluence_visuelle = st.slider("Confluence visuelle estimée (%) avant trypsine", 10, 100, 80, 5)
    concentration = st.number_input("Concentration mesurée (cellules/mL)", min_value=0, value=1200000, step=50000)

with col2:
    vol_final = st.number_input("Volume final de la nouvelle flasque (mL)", min_value=5, max_value=20, value=12)
    prochain_passage_date = st.date_input("Date du prochain passage souhaité", datetime.date.today() + datetime.timedelta(days=3))

# Nombre total de cellules dans le Falcon actuel
cellules_totales_falcon = concentration * VOLUME_FALCON

# Calcul du temps global en heures jusqu'au prochain passage
heures_totales = (prochain_passage_date - datetime.date.today()).days * 24
# Temps réel de prolifération (on retire le temps d'adhérence)
heures_proliferation_effective = heures_totales - TEMPS_ADHERENCE_H

if heures_proliferation_effective <= 0:
    st.error("⚠️ L'intervalle de temps choisi est trop court pour permettre l'adhérence et la multiplication des cellules.")
else:
    # --- CALCUL DE L'INOCULUM ---
    # Formule exponentielle basée uniquement sur le temps de prolifération effectif
    nb_cycles_division = heures_proliferation_effective / doubling_time_h
    cellules_a_ensemencer = CELLULES_CIBLE_80 / (2 ** nb_cycles_division)
    
    # Volume à prélever dans le Falcon de 12 mL
    vol_a_prelever_ml = cellules_a_ensemencer / concentration
    vol_milieu_frais_ml = vol_final - vol_a_prelever_ml
    ratio_cellulaire = (vol_a_prelever_ml / vol_final) * 100

    # --- AFFICHAGE DE LA RECETTE ---
    st.write("---")
    st.header("📋 Recette pour la nouvelle T75")
    
    # Alerte Sécurité : Moins de 10% (Trop dilué, risque de mort cellulaire par isolement)
    if ratio_cellulaire < 10.0:
        st.error(f"🚨 **Attention : Risque de mortalité ! Les cellules seront trop isolées.**")
        st.warning(f"Le volume de cellules requis ({ratio_cellulaire:.1f}%) est inférieur au seuil des 10%.")
        
        # Calcul du volume de triche
        vol_final_ajuste = vol_a_prelever_ml / 0.10
        st.info(f"💡 **Conseils de protocole :** \n"
                f"1. **Diminuez le volume final** de votre nouvelle flasque à **{vol_final_ajuste:.1f} mL** pour maintenir le ratio de 10%.  \n"
                f"2. Ou prélevez **{vol_a_prelever_ml*1000:.0f} µL** de cellules, complétez à 10 mL avec du milieu frais, centrifugez, aspirez et reprenez le culot dans vos **{vol_final:.1f} mL** de milieu final.")
    else:
        st.success(f"✅ **Ratio de viabilité optimal ({ratio_cellulaire:.1f}%)**")

    c1, c2, c3 = st.columns(3)
    c1.metric("Volume de cellules (Falcon)", f"{vol_a_prelever_ml*1000:.0f} µL" if vol_a_prelever_ml < 1 else f"{vol_a_prelever_ml:.2f} mL")
    c2.metric("Milieu DMEM-10% FBS neuf", f"{vol_milieu_frais_ml:.2f} mL")
    c3.metric("Pourcentage de suspension", f"{ratio_cellulaire:.1f} %")

    # --- ENREGISTREMENT ET APPRENTISSAGE RETROACTIF ---
    st.write("---")
    if st.button("💾 Enregistrer et Loguer le Passage"):
        
        dt_effectif = np.nan
        # Calcul rétroactif du vrai temps de doublement basé sur le passage précédent
        if not df_logs.empty:
            dernier_passage = df_logs.iloc[-1]
            cellules_initiales_prec = dernier_passage["Cellules_Ensemencees"]
            jours_ecoules = (datetime.date.today() - dernier_passage["Date"]).days
            
            if jours_ecoules > 0 and cellules_totales_falcon > cellules_initiales_prec:
                heures_ecoulees_totale = jours_ecoules * 24
                # On enlève le temps de latence au cycle précédent pour calculer le vrai taux de division
                heures_div_reelle = heures_ecoulees_totale - TEMPS_ADHERENCE_H
                if heures_div_reelle > 0:
                    dt_effectif = (heures_div_reelle * np.log(2)) / (np.log(cellules_totales_falcon) - np.log(cellules_initiales_prec))

        new_entry = {
            "Date": datetime.date.today(),
            "Confluence_Visuelle": confluence_visuelle,
            "Concentration_Mesuree": concentration,
            "Cellules_Totales_Recoltees": cellules_totales_falcon,
            "Cellules_Ensemencees": cellules_a_ensemencer,
            "Jours_Attendus": (prochain_passage_date - datetime.date.today()).days,
            "DT_Calcule": dt_effectif if not np.isnan(dt_effectif) else doubling_time_h
        }
        
        df_logs = pd.concat([df_logs, pd.DataFrame([new_entry])], ignore_index=True)
        save_data(df_logs)
        st.success("Passage logué ! L'algorithme a ajusté la vitesse de croissance.")
        st.rerun()

# --- HISTORIQUE ---
st.header("📜 Journal de bord des T75")
if not df_logs.empty:
    st.dataframe(df_logs.tail(10))
else:
    st.info("Aucun passage dans le log pour le moment.")
