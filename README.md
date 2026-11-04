# NEBULA CORE V2.5 — Synchronisation manuelle des séparateurs

## Installation
Remplacer `app.py`, `index.html`, `start.bat` et compléter `.gitignore`. Conserver `.env` et `data/`.

**Obligatoire :** Discord Developer Portal → Bot → Privileged Gateway Intents → **Server Members Intent** = ON. Le bot doit avoir **Gérer les rôles** et son rôle doit être au-dessus des séparateurs.

Onglet **Séparateurs auto** : configurer les groupes (séparateur + rôles déclencheurs), cliquer **Analyser tous les membres**, lire le décompte, puis **Appliquer à tous les membres**. Le traitement progresse en arrière-plan et peut durer plusieurs minutes.

- Analyse complète par `guild.fetch_members(limit=None)`, sans dépendre du cache.
- Ignore les bots et les rôles déjà présents.
- N'enlève jamais les rôles existants.
- Vérifie la hiérarchie du bot.
- Confirme sur un aperçu valable 5 minutes.
- Règles enregistrées dans `data/separator_mapping.json` (local, hors Git).
- Cette fonctionnalité est **manuelle**, pas un bot H24.
- La page web reste **locale** (`127.0.0.1:8765`).

La synchronisation traite tous les membres humains et applique les groupes indépendamment : un Haut Staff peut aussi recevoir le séparateur Staff s'il possède un rôle déclencheur Staff. Vérifier le mapping avant d'appliquer.
