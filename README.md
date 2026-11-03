# NEBULA CORE — Control Center V2

## Installation

1. Fermer l'ancienne instance avec Ctrl+C dans PowerShell.
2. Extraire le dossier V2.
3. Copier votre ancien fichier `.env` dans ce dossier (ne jamais le partager).
4. Ouvrir PowerShell dans ce dossier.
5. `python -m pip install -r requirements.txt`
6. `python app.py`
7. Ouvrir http://127.0.0.1:8765

## Nouvelles fonctions
- Interface bleu nuit/cyan repensée, navigation et recherches.
- Création en masse de salons et catégories.
- Renommage, déplacement et suppression de salons.
- Création, renommage, recoloration et suppression de rôles ; options d'affichage séparé et mentionnable.
- Permissions en masse multi-rôles, multi-salons et multi-permissions, avec tri-état (autoriser/refuser/neutre).
- Export de sauvegarde JSON.

## Sécurité et limites
- L'application est liée uniquement à 127.0.0.1 et n'est pas exposée sur le réseau.
- Le bot doit disposer des permissions Discord requises et d'une position de rôle suffisante.
- Les actions destructives demandent la saisie de SUPPRIMER.
- Les modifications en masse ne sont pas transactionnelles : une erreur peut survenir après quelques changements déjà effectués.
- L'export JSON ne restaure pas automatiquement le serveur.
- Les salons de type forum ne peuvent pas être convertis directement depuis un salon texte.
- Les permissions d'un rôle Administrateur peuvent contourner les restrictions de salon.
- Ne jamais partager le token ni le fichier `.env`.
