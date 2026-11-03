import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import discord
from discord.ext import commands
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN', '')
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', '0'))
if not TOKEN or not GUILD_ID:
    raise RuntimeError('Configure DISCORD_BOT_TOKEN et DISCORD_GUILD_ID dans .env')

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)
ready = asyncio.Event()

@bot.event
async def on_ready():
    print(f'Bot connecté : {bot.user}')
    ready.set()

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(bot.start(TOKEN))
    try:
        yield
    finally:
        await bot.close()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(title='Nebula Core', lifespan=lifespan)

async def guild():
    if not ready.is_set():
        raise HTTPException(503, 'Bot en cours de connexion')
    g = bot.get_guild(GUILD_ID)
    if not g:
        raise HTTPException(404, 'Serveur introuvable : vérifie DISCORD_GUILD_ID et invitation du bot')
    return g

@app.exception_handler(discord.Forbidden)
async def forbidden_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=403, content={'detail': 'Permission Discord insuffisante ou rôle du bot trop bas'})

@app.exception_handler(discord.HTTPException)
async def discord_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=502, content={'detail': f'Erreur Discord : {exc.text}'})

@app.get('/')
async def index():
    return FileResponse(Path(__file__).parent / 'index.html')

@app.get('/api/state')
async def state():
    g = await guild()
    return {
        'name': g.name,
        'roles': [{'id': str(r.id), 'name': r.name, 'color': str(r.color), 'position': r.position, 'managed': r.managed, 'hoist': r.hoist, 'mentionable': r.mentionable} for r in reversed(g.roles) if r != g.default_role],
        'categories': [{'id': str(c.id), 'name': c.name} for c in g.categories],
        'channels': [{'id': str(c.id), 'name': c.name, 'type': str(c.type), 'category_id': str(c.category_id) if c.category_id else None} for c in g.channels if not isinstance(c, discord.CategoryChannel)]
    }

class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = '#00d9ff'

@app.post('/api/roles')
async def create_role(payload: RoleCreate):
    g = await guild()
    try:
        color = discord.Color(int(payload.color.lstrip('#'), 16))
    except ValueError:
        raise HTTPException(400, 'Couleur hexadécimale invalide')
    role = await g.create_role(name=payload.name, color=color, reason='Nebula Core dashboard')
    return {'id': str(role.id), 'name': role.name}

class ChannelsCreate(BaseModel):
    names: str = Field(min_length=1)
    kind: Literal['text', 'voice', 'forum', 'news', 'category'] = 'text'
    category_id: str | None = None

@app.post('/api/channels')
async def create_channels(payload: ChannelsCreate):
    g = await guild()
    names = [n.strip() for n in payload.names.splitlines() if n.strip()]
    if not names or len(names) > 30:
        raise HTTPException(400, 'Entre 1 et 30 noms par opération')
    cat = None
    if payload.category_id:
        cat = g.get_channel(int(payload.category_id))
        if not isinstance(cat, discord.CategoryChannel):
            raise HTTPException(400, 'Catégorie invalide')
    if payload.kind == 'news' and not 'COMMUNITY' in [f.name for f in g.features]:
        raise HTTPException(400, 'Les salons annonces nécessitent le mode Communauté')
    results = []
    for name in names:
        if payload.kind == 'category':
            c = await g.create_category(name, reason='Nebula Core dashboard')
        elif payload.kind == 'voice':
            c = await g.create_voice_channel(name, category=cat, reason='Nebula Core dashboard')
        elif payload.kind == 'forum':
            c = await g.create_forum(name, category=cat, reason='Nebula Core dashboard')
        else:
            c = await g.create_text_channel(name, category=cat, news=(payload.kind == 'news'), reason='Nebula Core dashboard')
        results.append({'id': str(c.id), 'name': c.name})
    return {'created': results}

# Explicit tri-state overwrite: allow, deny, inherit.
class PermissionBatch(BaseModel):
    role_id: str
    channel_ids: list[str] = Field(min_length=1, max_length=100)
    permission: Literal['view_channel', 'send_messages', 'read_message_history', 'connect', 'speak', 'manage_messages', 'manage_channels', 'create_public_threads', 'send_messages_in_threads']
    value: Literal['allow', 'deny', 'inherit']

@app.post('/api/permissions/batch')
async def permission_batch(payload: PermissionBatch):
    g = await guild()
    role = g.get_role(int(payload.role_id))
    if not role:
        raise HTTPException(404, 'Rôle introuvable')
    channels = []
    for cid in payload.channel_ids:
        c = g.get_channel(int(cid))
        if c is None:
            raise HTTPException(404, f'Salon introuvable : {cid}')
        channels.append(c)
    value = {'allow': True, 'deny': False, 'inherit': None}[payload.value]
    for c in channels:
        overwrite = c.overwrites_for(role)
        setattr(overwrite, payload.permission, value)
        await c.set_permissions(role, overwrite=overwrite, reason='Nebula Core permissions en masse')
    return {'updated': len(channels)}

class ChannelUpdate(BaseModel):
    channel_id: str
    name: str | None = None
    category_id: str | None = None

@app.post('/api/channels/edit')
async def edit_channel(payload: ChannelUpdate):
    g = await guild()
    c = g.get_channel(int(payload.channel_id))
    if not c:
        raise HTTPException(404, 'Salon introuvable')
    kwargs = {}
    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(400, 'Nom vide')
        kwargs['name'] = payload.name.strip()
    if payload.category_id is not None:
        cat = g.get_channel(int(payload.category_id)) if payload.category_id else None
        if cat is not None and not isinstance(cat, discord.CategoryChannel):
            raise HTTPException(400, 'Catégorie invalide')
        if isinstance(c, discord.CategoryChannel):
            raise HTTPException(400, 'Impossible de déplacer une catégorie dans une catégorie')
        kwargs['category'] = cat
    if not kwargs:
        raise HTTPException(400, 'Aucune modification')
    await c.edit(**kwargs, reason='Nebula Core dashboard')
    return {'updated': str(c.id)}

@app.get('/api/backup')
async def backup():
    g = await guild()
    return {
        'guild': {'id': str(g.id), 'name': g.name},
        'roles': [{'id': str(r.id), 'name': r.name, 'color': str(r.color), 'permissions': r.permissions.value} for r in g.roles],
        'channels': [{'id': str(c.id), 'name': c.name, 'type': str(c.type), 'category_id': str(c.category_id) if getattr(c, 'category_id', None) else None, 'overwrites': {str(target.id): {'allow': allow.value, 'deny': deny.value} for target, (allow, deny) in c.overwrites.items()}} for c in g.channels]
    }

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8765)

# V2: maintenance endpoints
class RoleUpdate(BaseModel):
    role_id: str
    name: str | None = None
    color: str | None = None
    hoist: bool | None = None
    mentionable: bool | None = None

@app.post('/api/roles/edit')
async def update_role(payload: RoleUpdate):
    g = await guild()
    r = g.get_role(int(payload.role_id))
    if not r or r.is_default() or r.managed:
        raise HTTPException(400, 'Rôle non modifiable')
    changes = {}
    if payload.name is not None:
        if not payload.name.strip(): raise HTTPException(400, 'Nom vide')
        changes['name'] = payload.name.strip()
    if payload.color is not None:
        try: changes['color'] = discord.Color(int(payload.color.lstrip('#'), 16))
        except ValueError: raise HTTPException(400, 'Couleur invalide')
    if payload.hoist is not None: changes['hoist'] = payload.hoist
    if payload.mentionable is not None: changes['mentionable'] = payload.mentionable
    if not changes: raise HTTPException(400, 'Aucun changement')
    await r.edit(**changes, reason='Nebula Core V2')
    return {'updated': str(r.id)}

class DeleteItem(BaseModel):
    id: str
    confirmation: str

@app.post('/api/roles/delete')
async def delete_role(payload: DeleteItem):
    g = await guild()
    r = g.get_role(int(payload.id))
    if payload.confirmation != 'SUPPRIMER' or not r or r.is_default() or r.managed:
        raise HTTPException(400, 'Suppression non autorisée')
    await r.delete(reason='Nebula Core V2')
    return {'deleted': payload.id}

@app.post('/api/channels/delete')
async def delete_channel(payload: DeleteItem):
    g = await guild()
    c = g.get_channel(int(payload.id))
    if payload.confirmation != 'SUPPRIMER' or not c:
        raise HTTPException(400, 'Suppression non autorisée')
    await c.delete(reason='Nebula Core V2')
    return {'deleted': payload.id}

class PermissionMatrix(BaseModel):
    role_ids: list[str] = Field(min_length=1, max_length=20)
    channel_ids: list[str] = Field(min_length=1, max_length=100)
    permissions: dict[str, Literal['allow', 'deny', 'inherit']]

ALLOWED_PERMS = {'view_channel','send_messages','read_message_history','connect','speak','manage_messages','manage_channels','create_public_threads','send_messages_in_threads','attach_files','embed_links','add_reactions','manage_threads','create_private_threads','use_application_commands'}

@app.post('/api/permissions/matrix')
async def permission_matrix(payload: PermissionMatrix):
    g = await guild()
    if not payload.permissions or not set(payload.permissions).issubset(ALLOWED_PERMS):
        raise HTTPException(400, 'Permissions invalides')
    roles = [g.get_role(int(i)) for i in payload.role_ids]
    channels = [g.get_channel(int(i)) for i in payload.channel_ids]
    if any(r is None for r in roles) or any(c is None for c in channels):
        raise HTTPException(404, 'Rôle ou salon introuvable')
    updated = 0
    for c in channels:
        for r in roles:
            overwrite = c.overwrites_for(r)
            for permission, value in payload.permissions.items():
                setattr(overwrite, permission, {'allow': True, 'deny': False, 'inherit': None}[value])
            await c.set_permissions(r, overwrite=overwrite, reason='Nebula Core V2 matrice')
            updated += 1
    return {'updated': updated}
