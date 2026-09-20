import fs from 'node:fs'
import path from 'node:path'
import { Buffer } from 'node:buffer'
import { createDashboardReadModel, createEnvelope } from './dashboardReadModel.js'
import { createDashboardEventStream } from './dashboardEventStream.js'
import { createGalleryReadModel } from './galleryReadModel.js'
import { sanitizeDashboardPayload } from './dashboardSanitizer.js'
import { validateStrategyDraft } from './strategyDraftValidator.js'

const IMAGE_TYPES = Object.freeze({ '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.gif': 'image/gif', '.avif': 'image/avif' })
export const AUTHORIZED_ENDPOINTS = Object.freeze([
  'GET /api/v1/health', 'GET /api/v1/capabilities', 'GET /api/v1/dashboard/snapshot', 'GET /api/v1/dashboard/events',
  'GET /api/v1/market-drivers', 'GET /api/v1/broker/status', 'GET /api/v1/maintenance/status', 'GET /api/v1/about',
  'GET /api/v1/about/gallery', 'GET /api/v1/about/gallery/items/:id/image', 'POST /api/v1/strategy-drafts/validate',
])

function sendJson(response, status, value) {
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  response.end(JSON.stringify(sanitizeDashboardPayload(value)))
}

async function readJsonBody(request, maxBytes = 32 * 1024) {
  let raw = ''
  for await (const chunk of request) {
    raw += chunk
    if (Buffer.byteLength(raw) > maxBytes) throw new Error('REQUEST_TOO_LARGE')
  }
  return raw ? JSON.parse(raw) : {}
}

export function isLoopbackHostname(hostHeader = '') {
  const hostname = String(hostHeader).split(':')[0].replace(/^\[|\]$/g, '').toLowerCase()
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1'
}

export function buildCapabilities(hostHeader, galleryEnabled = false) {
  return {
    authentication: { microsoft: 'NOT CONFIGURED', github: 'NOT CONFIGURED', passkey: 'NOT CONFIGURED', security_key: 'NOT CONFIGURED' },
    local_preview_available: isLoopbackHostname(hostHeader), trade_execution: false, shell_execution: false,
    broker_connection: false, gallery: galleryEnabled,
  }
}

export function createDashboardApi({
  dashboardRoot,
  galleryRoot = path.join(dashboardRoot, 'private-media', 'service-gallery'),
  requireDataAccess = () => true,
} = {}) {
  const readModel = createDashboardReadModel(dashboardRoot)
  const gallery = createGalleryReadModel(galleryRoot)
  const events = createDashboardEventStream({ snapshot: readModel.snapshot })

  return async function handleDashboardApi(request, response) {
    const url = new URL(request.url, 'http://localhost')
    const route = url.pathname
    if (!route.startsWith('/api/v1/')) return false

    if (request.method === 'GET' || request.method === 'HEAD') {
      if (route === '/api/v1/health') return sendJson(response, 200, createEnvelope({ source: 'runtime', mode: 'LIVE_BLOCKED', freshness: 'FRESH', data: { service: 'AIOS dashboard', state: 'READY', read_only: true } })), true
      if (route === '/api/v1/capabilities') return sendJson(response, 200, createEnvelope({ source: 'runtime', mode: 'LIVE_BLOCKED', freshness: 'FRESH', data: buildCapabilities(request.headers.host, gallery.list().enabled) })), true
      if (!requireDataAccess(request, response)) return true
      if (route === '/api/v1/dashboard/snapshot') return sendJson(response, 200, readModel.snapshot()), true
      if (route === '/api/v1/dashboard/events') { events(request, response); return true }
      if (route === '/api/v1/market-drivers') return sendJson(response, 200, readModel.marketDrivers()), true
      if (route === '/api/v1/broker/status') return sendJson(response, 200, readModel.brokerStatus()), true
      if (route === '/api/v1/maintenance/status') return sendJson(response, 200, readModel.maintenanceStatus()), true
      if (route === '/api/v1/about') return sendJson(response, 200, readModel.about()), true
      if (route === '/api/v1/about/gallery') return sendJson(response, 200, createEnvelope({ source: gallery.list().enabled ? 'runtime' : 'unavailable', mode: 'UNKNOWN', data: gallery.list() })), true
      const imageMatch = route.match(/^\/api\/v1\/about\/gallery\/items\/([a-f0-9]{20})\/image$/)
      if (imageMatch) {
        if (!isLoopbackHostname(request.headers.host)) { sendJson(response, 403, { status: 'BLOCKED', reason: 'LOCAL_PRIVATE_MEDIA_LOOPBACK_ONLY' }); return true }
        const item = gallery.resolveItem(imageMatch[1])
        if (!item) { sendJson(response, 404, { status: 'UNAVAILABLE' }); return true }
        response.writeHead(200, { 'content-type': IMAGE_TYPES[item.extension] ?? 'application/octet-stream', 'cache-control': 'private, no-store' })
        if (request.method === 'HEAD') response.end(); else fs.createReadStream(item.filePath).pipe(response)
        return true
      }
    }

    if (request.method === 'POST' && route === '/api/v1/strategy-drafts/validate') {
      if (!requireDataAccess(request, response)) return true
      try {
        const draft = await readJsonBody(request)
        sendJson(response, 200, createEnvelope({ source: 'runtime', mode: 'UNKNOWN', freshness: 'FRESH', data: validateStrategyDraft(draft) }))
      } catch (error) {
        sendJson(response, error?.message === 'REQUEST_TOO_LARGE' ? 413 : 400, createEnvelope({ source: 'runtime', mode: 'UNKNOWN', data: { status: 'INVALID', errors: ['Invalid request body.'] } }))
      }
      return true
    }

    sendJson(response, request.method === 'GET' || request.method === 'HEAD' || request.method === 'POST' ? 404 : 405, { status: 'UNAVAILABLE', reason: 'ENDPOINT_NOT_AUTHORIZED' })
    return true
  }
}
