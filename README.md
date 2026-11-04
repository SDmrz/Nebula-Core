# NEBULA CORE V2.3 — Aurora+

**Fonctionne uniquement lorsque tu lances `start.bat`** : aucune configuration H24.

## Nouveautés
- Kits de rôles staff et séparateurs visuels NEBULA, sélection multiple, couleur et aperçu, confirmation avant création.
- Les rôles existants sont ignorés. Les nouveaux rôles sont créés **sans permissions**, non mentionnables.
- Palette de navigation Ctrl+K (recherche, flèches, Entrée, Échap).
- Retour sur le dernier onglet ouvert lors d'un rafraîchissement (session du navigateur).
- Animations et composants visuels affinés.
- `/api/health` pour distinguer dashboard actif et bot Discord connecté.
- Règlement, gestion des salons, permissions, historique et export conservés.

## Installation
Remplace `app.py`, `index.html`, `start.bat` et `.gitignore` (ou fusionne tes règles d'ignore). **Ne remplace jamais `.env` ni le dossier `data/`.**

Sur ton PC principal, après avoir sauvegardé tes modifications :
```
git add app.py index.html start.bat .gitignore
git commit -m "NEBULA CORE V2.3 Aurora+"
git push origin main
```
Sur le second PC, ton lanceur fait `git pull --ff-only`.

**Attention** : le dashboard est conçu pour `127.0.0.1` en local. Ne l'expose pas directement sur Internet sans authentification.
