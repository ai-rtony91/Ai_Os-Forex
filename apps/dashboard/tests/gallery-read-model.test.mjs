import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { createGalleryReadModel } from '../server/galleryReadModel.js'

test('gallery rejects traversal and unsupported extensions while staying inside fixed root', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'aios-gallery-'))
  try {
    fs.writeFileSync(path.join(root, 'approved.png'), Buffer.from('fixture'))
    fs.writeFileSync(path.join(root, 'gallery.local.json'), JSON.stringify({ items: [
      { title: 'Approved', file: 'approved.png' }, { title: 'Traversal', file: '../private.jpg' }, { title: 'Text', file: 'notes.txt' },
    ] }))
    const gallery = createGalleryReadModel(root)
    const listing = gallery.list()
    assert.equal(listing.items.length, 1)
    const resolved = gallery.resolveItem(listing.items[0].id)
    assert.ok(resolved.filePath.startsWith(`${path.resolve(root)}${path.sep}`))
    assert.equal(path.extname(resolved.filePath), '.png')
    assert.doesNotMatch(JSON.stringify(listing), new RegExp(root.replaceAll('\\', '\\\\')))
  } finally { fs.rmSync(root, { recursive: true, force: true }) }
})

test('gallery unavailable state does not enumerate a directory', () => {
  const gallery = createGalleryReadModel(path.join(os.tmpdir(), 'aios-gallery-missing'))
  assert.deepEqual(gallery.list().items, [])
  assert.equal(gallery.list().enabled, false)
})
