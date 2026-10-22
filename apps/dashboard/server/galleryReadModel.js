import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

export const APPROVED_IMAGE_EXTENSIONS = Object.freeze(new Set(['.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif']))

function opaqueId(fileName) {
  return crypto.createHash('sha256').update(fileName).digest('hex').slice(0, 20)
}

function normalizeEntry(entry) {
  if (!entry || typeof entry !== 'object') return null
  const fileName = entry.file ?? entry.filename ?? entry.src
  if (typeof fileName !== 'string' || fileName !== path.basename(fileName)) return null
  if (!APPROVED_IMAGE_EXTENSIONS.has(path.extname(fileName).toLowerCase())) return null
  if (typeof entry.title !== 'string' || !entry.title.trim()) return null
  return { id: opaqueId(fileName), title: entry.title.trim(), fileName }
}

export function createGalleryReadModel(galleryRoot) {
  const fixedRoot = path.resolve(galleryRoot)
  const manifestPath = path.join(fixedRoot, 'gallery.local.json')

  function list() {
    try {
      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
      if (manifest?.enabled === false) return { enabled: false, label: 'LOCAL PRIVATE MEDIA', items: [], state: 'DISABLED' }
      const rawEntries = Array.isArray(manifest) ? manifest : (manifest.items ?? manifest.gallery ?? [])
      const entries = rawEntries.map(normalizeEntry).filter(Boolean)
      return {
        enabled: true,
        label: 'LOCAL PRIVATE MEDIA',
        items: entries.map(({ id, title }) => ({ id, title, image_url: `/api/v1/about/gallery/items/${id}/image` })),
      }
    } catch {
      return { enabled: false, label: 'LOCAL PRIVATE MEDIA', items: [], state: 'UNAVAILABLE' }
    }
  }

  function resolveItem(id) {
    const listing = list()
    if (!listing.enabled) return null
    let manifest
    try { manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8')) } catch { return null }
    if (manifest?.enabled === false) return null
    const rawEntries = Array.isArray(manifest) ? manifest : (manifest.items ?? manifest.gallery ?? [])
    const entry = rawEntries.map(normalizeEntry).find((item) => item?.id === id)
    if (!entry) return null
    const filePath = path.resolve(fixedRoot, entry.fileName)
    if (!filePath.startsWith(`${fixedRoot}${path.sep}`)) return null
    if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) return null
    return { filePath, extension: path.extname(filePath).toLowerCase() }
  }

  return { list, resolveItem, fixedRoot, manifestPath }
}
