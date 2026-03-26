# Tableau Kanban Hybride : SAS → Python/PySpark
## Basé sur le Planning Officiel (Semaines 1 à 14)

> **Règle de Gestion** : Flux Kanban appliqué au plan Scrum (Sprints hébdomadaires).  
> **Contrainte Active** : WIP limit = 2 (2 tâches concurrentes max) en phase "En Cours".
> **Statut Actuel** : Sprint / Semaine 2 

### Légende des Priorités
* 🔴 **P0** : Infrastructure Core (Bloquant)
* 🟠 **P1** : Agents RAPTOR & Persistance (Critique)
* 🟡 **P2** : Traduction, Merge & Base de connaissances (Moyen)
* 🔵 **P3** : Finitions, CI/CD, Démo (Basse)

---

## 🟢 TERMINÉ (Semaine 1)

| Semaine | Livrable (Couche) | Checklist Technique (À faire) | Temps Estimé | Succès | Priorité |
|:---:|:---|:---|:---:|:---|:---:|
| **1–2** | **L2-A : Entry & Scan**<br>*(FileAnalysisAgent, CrossFileDependencyResolver, RegistryWriterAgent, DataLineageExtractor)* | <ul><li>[x] Scanner les fichiers (detect encoding)</li><li>[x] Extraire dépendances (`%INCLUDE`) et lignage</li><li>[x] Écrire dans DB SQLite (`file_registry`)</li></ul> | **2.5 Jours** | 50 fichiers scannés (SQLite OK) | 🔴 P0 |
| **1–2** | **Création du "Gold Standard"** | <ul><li>[x] Coder 15 SAS Simples, 20 Moyens, 15 Complexes</li><li>[x] Annoter manuellement 721 sous-blocs en JSON</li></ul> | **2.5 Jours** | 721 partitions annotées | 🔴 P0 |

---

## 🔄 EN COURS (Semaine 2 — Sprint Actuel)
*(WIP Limit : Ne tirez qu'une carte à la fois)*

| Semaine | Livrable (Couche) | Checklist Technique (À faire) | Temps Estimé | Succès | Priorité |
|:---:|:---|:---|:---:|:---|:---:|
| **2–3** | **L2-B : Streaming Core**<br>*(StreamAgent)* | <ul><li>[ ] Boucle asynchrone `aiofiles`</li><li>[ ] Séparation logique par point-virgule (buffer)</li><li>[ ] Gestion Backpressure (Queue limits)</li></ul> | **3 Jours** | Fichier 10K lignes traité < 2 sec | 🔴 P0 |
| **2–3** | **L2-B : Moteur d'État FSM**<br>*(StateAgent)* | <ul><li>[ ] Définir états (`GLOBAL`, `IN_MACRO`, `IN_DATA`, `IN_SQL`)</li><li>[ ] Coder les transitions basées sur mots-clés SAS</li><li>[ ] Attacher l'état actif à chaque Chunk streamé</li></ul> | **2 Jours** | Pic RAM < 100 MB garanti | 🔴 P0 |

---

## 📋 À FAIRE / BACKLOG (Semaines 3 à 14)

| Semaine | Livrable (Couche) | Checklist Technique (À faire) | Temps Estimé | Succès | Priorité |
|:---:|:---|:---|:---:|:---|:---:|
| **3–4** | **L2-C : Détection de Frontières**<br>*(BoundaryDetectorAgent)* | <ul><li>[ ] Intégrer la grammaire `sas.lark`</li><li>[ ] Coder la détection de blocs valides exclusifs</li><li>[ ] Coder l’appel LLM Azure pour les cas ambigus</li></ul> | **3.5 Jours** | Benchmark > 90% précision de découpe | 🔴 P0 |
| **4** | **L2-D : Modélisation Complexité**<br>*(ComplexityAgent, StrategyAgent)* | <ul><li>[ ] Extraire 5 features d'analyse SAS</li><li>[ ] Entraîner classifieur Logistic Regression</li><li>[ ] Calibrer probabilité (Platt scaling)</li></ul> | **3 Jours** | ECE (Erreur Calibration) < 0.08 | 🔴 P0 |
| **5** | **L2-C-A : Modélisation Vectorielle**<br>*(RAPTORPartitionAgent)* | <ul><li>[ ] Intégrer modèle local `Nomic Embed` pour vectorisation</li><li>[ ] Exporter vecteurs 768-dim en cache SQLite/LanceDB</li></ul> | **3.5 Jours** | 100% des blocs vectorisés | 🟠 P1 |
| **6** | **L2-C-B : Algorithme RAPTOR**<br>*(RAPTORPartitionAgent)* | <ul><li>[ ] Coder GMM Clustering (optimisation auto BIC)</li><li>[ ] Résumer grappes via appel Azure OpenAI (GPT-4 mini)</li></ul> | **3.5 Jours** | Convergence BIC atteinte | 🟠 P1 |
| **7** | **L2-E : Indexation Graphes**<br>*(PersistenceAgent, IndexAgent)* | <ul><li>[ ] Construire `nx.DiGraph` (arêtes `DEPENDS_ON`/`MACRO_CALLS`)</li><li>[ ] Implémenter l'alerte SCC (cycles d'inclusions infinis)</li><li>[ ] Créer schémas cible base vectorielle (LanceDB/DuckDB)</li></ul> | **5 Jours** | Detection SCC ≥ 90% | 🟠 P1 |
| **8** | **Orchestrateur LangGraph**<br>*(PartitionOrchestrator)* | <ul><li>[ ] Remplacer flow linéaire par StateGraph asynchrone</li><li>[ ] Activer checkpoints Redis automatiques</li><li>[ ] Initialiser la table de logs d'audits (DuckDB)</li></ul> | **4 Jours** | Exécution asynchrone de bout-en-bout | 🟠 P1 |
| **9** | **Robustesse & Base de Connaissances**<br>*(KB Generation)* | <ul><li>[ ] Coder le failover sur `flat_partition` pour gros fichiers</li><li>[ ] Azure LLM (Traducteur) vs Groq LLM (Juge validateur)</li><li>[ ] Stocker paires dont le score de confiance > 0.85</li></ul> | **4.5 Jours** | 250 paires KB ("Gold") stockées | 🟡 P2 |
| **10** | **L3 : pipeline RAG de Traduction**<br>*(TranslationAgent, ValidationAgent)* | <ul><li>[ ] Routage auto : StaticRAG, AgentRAG, GraphRAG</li><li>[ ] Règles prompts expertes (mots clés type RETAIN)</li><li>[ ] Sandbox: `exec()` code Python vs Faux DataFrames</li></ul> | **5 Jours** | Traduction validée ≥ 70% | 🟡 P2 |
| **11** | **L4 : Fusion, Rapports & Apprentissage**<br>*(MergeAgent, ReportAgent)* | <ul><li>[ ] `ImportConsolidator` (remonter tous les imports)</li><li>[ ] Générer rapport d'audit Markdown final / CodeBLEU</li><li>[ ] Monitorer la dérive (drift) LLM pour ré-entraînement</li></ul> | **4 Jours** | Scripts Python syntaxiquement valides | 🟡 P2 |
| **12** | **Étude d'Ablation PFE**<br>*(Evaluation Layer)* | <ul><li>[ ] Lancer 721 requêtes Benchmark "RAPTOR vs Flat"</li><li>[ ] Extraire Hit-Rates à n=5</li><li>[ ] Exporter graphiques pyplot (latence, précision par niveau)</li></ul> | **5 Jours** | Hit-rate RAPTOR > 0.82 | 🟡 P2 |
| **13** | **CI/CD & Consolidation**<br>*(Clean-up Enterprise)* | <ul><li>[ ] Condenser base 21 agents vers architectures à 8 gros noeuds</li><li>[ ] Ajouter Télémétrie Azure Monitor & OpenTelemetry</li><li>[ ] Rédiger Workflow GitHub Actions + CodeQL CI + Docker</li></ul> | **5 Jours** | Architecture stabilisée v3.0, 200 Tests OK | 🔵 P3 |
| **14** | **Soutenance Master** | <ul><li>[ ] Générer 50 dernières paires KB d'entreprise</li><li>[ ] Finaliser les 20 slides PPT d'architecture/résultats</li><li>[ ] Enregistrer 4 min vidéo de flux de conversion final UI</li></ul> | **5 Jours** | Documents PFE officiels validés | 🔵 P3 |
