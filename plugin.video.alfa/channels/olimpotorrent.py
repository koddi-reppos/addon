# -*- coding: utf-8 -*-

import sys, re
PY3 = False
if sys.version_info[0] >= 3: 
    PY3 = True
    unicode = str
    unichr = chr
    long = int
    from urllib.parse import urlparse, parse_qs, quote
else:
    from urlparse import urlparse, parse_qs
    from urllib import quote

from channelselector import get_thumb
from modules import autoplay
from modules import filtertools
from core import httptools
from core import scrapertools
from core import servertools
from core import tmdb
from core.item import Item
from platformcode import config, logger

# Configuración del canal
IDIOMAS = {'Latino': 'lat', 'Español': 'esp', 'Dual': 'dual'}
list_language = list(IDIOMAS.values())
list_quality = ['4K', '1080p', '720p', 'WEB-DL', 'DVDRip', 'BluRay']
list_servers = ['elementum']

canonical = {
    'channel': 'olimpotorrent',
    'host': config.get_setting("current_host", 'olimpotorrent', default=''),
    'host_alt': ["https://olimpotorrent.net"],
    'host_black_list': [],
    'set_tls': True, 
    'set_tls_min': True, 
    'retries_cloudflare': 3,
    'CF': True, 
    'CF_test': False, 
    'alfa_s': True
}

host = canonical['host'] or canonical['host_alt'][0]
__channel__ = canonical['channel']
encoding = "utf-8"

def join_url(base_url, path):
    """Helper para concatenar URLs correctamente"""
    if path.startswith('http'):
        return path
    elif path.startswith('/'):
        return base_url + path
    else:
        return base_url.rstrip('/') + '/' + path.lstrip('/')

def mainlist(item):
    logger.info()
    autoplay.init(item.channel, list_servers, list_quality)
    
    itemlist = []
    
    itemlist.append(Item(
        channel=item.channel, 
        title="Novedades", 
        action="peliculas", 
        url=host + "/peliculas/",
        thumbnail=get_thumb("newest", auto=True)
    ))
    
    itemlist.append(Item(
        channel=item.channel, 
        title="Buscar", 
        action="search", 
        url=host + "/?s=",
        thumbnail=get_thumb("search", auto=True)
    ))
    
    itemlist.append(Item(
        channel=item.channel, 
        title="", 
        action=""
    ))
    
    itemlist.append(Item(
        channel=item.channel, 
        title="[COLOR yellow]NOTA: Enlaces magnet para cliente torrent[/COLOR]", 
        action=""
    ))
    
    autoplay.show_option(item.channel, itemlist)
    
    return itemlist

def newest(categoria):
    logger.info()
    itemlist = []
    item = Item()
    
    try:
        if categoria in ['peliculas', 'latino']:
            item.url = host + "/peliculas/"
            itemlist = peliculas(item)
            # Filtrar solo contenido reproducible (no paginación ni navegación)
            itemlist = [i for i in itemlist if i.action == "findvideos"]
            # Limitar a primeros 15 elementos para newest
            if len(itemlist) > 15:
                itemlist = itemlist[:15]
    except Exception as e:
        logger.error("Error en newest: %s" % str(e))
        return []
        
    return itemlist

def search(item, texto):
    logger.info()
    
    if not texto:
        return []
    
    texto = texto.replace(" ", "+")
    item.url = host + "/?s=" + texto
    
    return buscar_peliculas(item)

def peliculas(item):
    logger.info()
    
    itemlist = []
    
    try:
        data = httptools.downloadpage(item.url, encoding=encoding, canonical=canonical).data
        
        # Buscar posts/artículos de películas con contexto más específico
        # Patrón 1: Enlaces dentro de títulos de posts
        patron = r'<(?:h[1-4]|div)[^>]*(?:class="[^"]*(?:title|post|entry)[^"]*"[^>]*)?[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([^<]{3,})</a>\s*</(?:h[1-4]|div)>'
        matches = re.findall(patron, data, re.IGNORECASE)
        
        # Patrón 2: Si no encuentra, buscar en contenedores de posts
        if not matches:
            patron_post = r'<(?:article|div)[^>]*class="[^"]*(?:post|entry|movie)[^"]*"[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>([^<]{3,})</a>.*?</(?:article|div)>'
            matches = re.findall(patron_post, data, re.IGNORECASE | re.DOTALL)
        
        for url, title in matches:
            url = join_url(host, url)
                
            title = scrapertools.htmlclean(title).strip()
            
            if title and url:
                itemlist.append(Item(
                    channel=item.channel,
                    action="findvideos",
                    title=title,
                    contentTitle=title,
                    url=url,
                    contentType="movie",
                    thumbnail="",
                    infoLabels={'year': '-'}
                ))
        
        # Si no encontramos películas con el patrón específico, intentar patrón genérico
        if not itemlist:
            patron_generico = r'<a[^>]*href="([^"]+)"[^>]*title="([^"]*)"[^>]*>'
            matches = re.findall(patron_generico, data, re.IGNORECASE)
            
            for url, title in matches:
                # Verificar que sea una URL relevante (no de menú o footer)
                if any(keyword in url.lower() for keyword in ['pelicula', 'torrent', 'download', 'ver-', 'movie']) and title:
                    if not url.startswith('http'):
                        url = join_url(host, url)
                    
                    title = scrapertools.htmlclean(title).strip()
                    
                    itemlist.append(Item(
                        channel=item.channel,
                        action="findvideos", 
                        title=title,
                        contentTitle=title,
                        url=url,
                        contentType="movie",
                        thumbnail="",
                        infoLabels={'year': '-'}
                    ))
        
        # Buscar enlaces de paginación
        patron_next = r'<a[^>]*href="([^"]*)"[^>]*>(?:Siguiente|Next|&gt;|›)</a>|<a[^>]*class="[^"]*next[^"]*"[^>]*href="([^"]*)"'
        next_matches = re.findall(patron_next, data, re.IGNORECASE)
        
        if next_matches:
            for next_url in next_matches[0]:
                if next_url:
                    next_url = join_url(host, next_url)
                    
                    itemlist.append(Item(
                        channel=item.channel,
                        action="peliculas",
                        title="Siguiente >>>",
                        url=next_url,
                        thumbnail=get_thumb("next", auto=True)
                    ))
                    break
        
        # Configurar información con TMDB
        tmdb.set_infoLabels_itemlist(itemlist, True)
        
    except Exception as e:
        logger.error("Error al obtener películas: %s" % str(e))
        
    return itemlist

def buscar_peliculas(item):
    logger.info()
    
    itemlist = []
    
    try:
        data = httptools.downloadpage(item.url, encoding=encoding, canonical=canonical).data
        
        # Buscar resultados de búsqueda usando los mismos patrones mejorados
        patron = r'<(?:h[1-4]|div)[^>]*(?:class="[^"]*(?:title|post|entry)[^"]*"[^>]*)?[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([^<]{3,})</a>\s*</(?:h[1-4]|div)>'
        matches = re.findall(patron, data, re.IGNORECASE)
        
        # Patrón fallback si no encuentra
        if not matches:
            patron_fallback = r'<h[0-9][^>]*><a[^>]*href="([^"]+)"[^>]*>([^<]+)</a></h[0-9]>'
            matches = re.findall(patron_fallback, data, re.IGNORECASE)
        
        for url, title in matches:
            url = join_url(host, url)
                
            title = scrapertools.htmlclean(title).strip()
            
            if title and url:
                itemlist.append(Item(
                    channel=item.channel,
                    action="findvideos",
                    title=title,
                    contentTitle=title,
                    url=url,
                    contentType="movie", 
                    thumbnail="",
                    infoLabels={'year': '-'}
                ))
        
        # Si no hay resultados con el patrón específico, intentar patrón más amplio
        if not itemlist:
            patron_amplio = r'href="([^"]+)"[^>]*>([^<]+)<'
            matches = re.findall(patron_amplio, data, re.IGNORECASE)
            
            for url, title in matches:
                url = join_url(host, url)
                
                title = scrapertools.htmlclean(title).strip()
                
                # Filtrar URLs relevantes para películas
                if any(keyword in url.lower() for keyword in ['pelicula', 'torrent', 'download', 'ver-', 'movie']) and title and len(title) > 3:
                    itemlist.append(Item(
                        channel=item.channel,
                        action="findvideos",
                        title=title,
                        contentTitle=title,
                        url=url,
                        contentType="movie",
                        thumbnail="",
                        infoLabels={'year': '-'}
                    ))
        
        # Configurar información con TMDB
        tmdb.set_infoLabels_itemlist(itemlist, True)
        
    except Exception as e:
        logger.error("Error en búsqueda: %s" % str(e))
        
    return itemlist

def findvideos(item):
    logger.info()
    
    itemlist = []
    
    try:
        data = httptools.downloadpage(item.url, encoding=encoding, canonical=canonical).data
        
        # Buscar enlaces magnet en la página (soporta hex y base32)
        patron_magnet = r'magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^"\'<>\s]*|magnet:\?xt=urn:btih:[A-Z2-7]{32}[^"\'<>\s]*'
        magnets = re.findall(patron_magnet, data, re.IGNORECASE)
        
        # También buscar en atributos data-*
        patron_data = r'data-[^=]*="(magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^"]*|magnet:\?xt=urn:btih:[A-Z2-7]{32}[^"]*)"'
        data_magnets = re.findall(patron_data, data, re.IGNORECASE)
        magnets.extend(data_magnets)
        
        # Deduplicar enlaces
        magnets = list(set(magnets))
        
        # Buscar en onclick
        patron_onclick = r'onclick="[^"]*magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^"]*"|onclick="[^"]*magnet:\?xt=urn:btih:[A-Z2-7]{32}[^"]*"'
        onclick_matches = re.findall(patron_onclick, data, re.IGNORECASE)
        for onclick in onclick_matches:
            magnet_match = re.search(r'magnet:\?xt=urn:btih:[a-fA-F0-9]{40}[^"]*|magnet:\?xt=urn:btih:[A-Z2-7]{32}[^"]*', onclick)
            if magnet_match:
                magnets.append(magnet_match.group(0))
        
        # Procesar cada enlace magnet encontrado
        for magnet_url in magnets:
            if not magnet_url.startswith('magnet:'):
                continue
                
            # Extraer información del nombre del archivo en el magnet
            try:
                parsed = urlparse(magnet_url)
                query_params = parse_qs(parsed.query)
                filename = query_params.get('dn', [''])[0]
            except:
                filename = "Archivo Torrent"
            
            # Extraer calidad del nombre del archivo
            quality = "Desconocida"
            if filename:
                if '4K' in filename.upper() or '2160p' in filename.upper():
                    quality = "4K"
                elif '1080p' in filename.upper():
                    quality = "1080p" 
                elif '720p' in filename.upper():
                    quality = "720p"
                elif 'WEB-DL' in filename.upper():
                    quality = "WEB-DL"
                elif 'BluRay' in filename.upper() or 'BLURAY' in filename.upper():
                    quality = "BluRay"
                elif 'DVDRIP' in filename.upper():
                    quality = "DVDRip"
            
            # Extraer idioma y asignar código
            language = "lat"  # Por defecto Latino
            if filename:
                if 'latino' in filename.lower() or 'lat' in filename.lower():
                    language = "lat"
                elif 'español' in filename.lower() or 'esp' in filename.lower() or 'castellano' in filename.lower():
                    language = "esp"
                elif 'dual' in filename.lower():
                    language = "dual"
            
            # Extraer tamaño aproximado
            size = "Desconocido"
            size_match = re.search(r'(\d+(?:\.\d+)?)\s*(GB|MB)', filename, re.IGNORECASE)
            if size_match:
                size = size_match.group(0)
            
            # Crear título descriptivo
            title = "[COLOR cyan]%s[/COLOR] " % quality
            if size != "Desconocido":
                title += "[COLOR yellow]%s[/COLOR] " % size
            # Convertir código de idioma a nombre para mostrar
            language_name = {v: k for k, v in IDIOMAS.items()}.get(language, "Latino")
            title += "[COLOR lime](%s)[/COLOR] " % language_name
            title += "TORRENT"
            
            # Crear URL para Elementum si está disponible
            elementum_url = "plugin://plugin.video.elementum/play?uri=" + quote(magnet_url)
            
            itemlist.append(Item(
                channel=item.channel,
                action="play",
                title=title,
                url=elementum_url,
                server="elementum",
                contentTitle=item.contentTitle,
                contentThumbnail=item.thumbnail,
                quality=quality,
                language=language,
                magnet_url=magnet_url,
                filename=filename,
                infoLabels=item.infoLabels
            ))
        
        # Si no se encontraron magnets, buscar en todo el HTML de forma más agresiva
        if not itemlist:
            # Decodificar entidades HTML que puedan contener magnets
            data_clean = scrapertools.htmlclean(data)
            patron_magnet_amplio = r'magnet:\?[^\s<>"\']*'
            magnets_amplio = re.findall(patron_magnet_amplio, data_clean, re.IGNORECASE)
            
            for magnet_url in magnets_amplio:
                if 'xt=urn:btih:' in magnet_url:
                    try:
                        parsed = urlparse(magnet_url)
                        query_params = parse_qs(parsed.query)
                        filename = query_params.get('dn', ['Torrent'])[0]
                    except:
                        filename = "Torrent"
                    
                    elementum_url = "plugin://plugin.video.elementum/play?uri=" + quote(magnet_url)
                    
                    itemlist.append(Item(
                        channel=item.channel,
                        action="play",
                        title="[COLOR lime]TORRENT[/COLOR] - " + filename,
                        url=elementum_url,
                        server="elementum",
                        contentTitle=item.contentTitle,
                        contentThumbnail=item.thumbnail,
                        magnet_url=magnet_url,
                        filename=filename,
                        infoLabels=item.infoLabels
                    ))
        
        # Aplicar filtros
        itemlist = filtertools.get_links(itemlist, item, list_language)
        
        # Configurar autoplay
        autoplay.start(itemlist, item)
        
        if not itemlist:
            itemlist.append(Item(
                channel=item.channel,
                title="[COLOR red]No se encontraron enlaces magnet[/COLOR]",
                action=""
            ))
        
    except Exception as e:
        logger.error("Error al buscar videos: %s" % str(e))
        itemlist.append(Item(
            channel=item.channel,
            title="[COLOR red]Error: %s[/COLOR]" % str(e),
            action=""
        ))
    
    return itemlist

def play(item):
    logger.info()
    
    # Devolver el item con la URL de Elementum para reproducción
    item.thumbnail = item.contentThumbnail
    return [item]