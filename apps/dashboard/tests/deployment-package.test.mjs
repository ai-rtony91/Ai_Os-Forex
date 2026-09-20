import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const dashboardRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

test('deployment package is rooted at dist with server.js startup and production dependency lockfile', () => {
  const viteConfig = fs.readFileSync(path.join(dashboardRoot, 'vite.config.js'), 'utf8')
  assert.match(viteConfig, /start: 'node server\.js'/)
  assert.match(viteConfig, /'package-lock\.json'/)
  assert.match(viteConfig, /dependencies:\s*{\s*jose:/s)
  assert.doesNotMatch(viteConfig, /'package\.json',[\r\n]/)
})

test('browser bundle uses sample autonomy data only and does not serialize local runtime files', () => {
  const viteConfig = fs.readFileSync(path.join(dashboardRoot, 'vite.config.js'), 'utf8')
  assert.match(viteConfig, /Build-time browser bundle uses sample data only/)
  assert.doesNotMatch(viteConfig, /AIOS_AUTONOMY_BRIDGE_STATE_PATH/)
  assert.doesNotMatch(viteConfig, /telemetry\/night_supervisor\/AUTONOMY_BRIDGE_STATE\.json/)
  assert.doesNotMatch(viteConfig, /sourceLabel: 'LIVE'/)
})

test('server normalizes encoded static paths before applying protected file blocks', () => {
  const serverSource = fs.readFileSync(path.join(dashboardRoot, 'server.js'), 'utf8')
  assert.match(serverSource, /normalizeStaticPath\(pathname\)/)
  assert.match(serverSource, /decodeURIComponent\(pathname\)/)
  assert.match(serverSource, /isBlockedStaticPath\(decodedPath\)/)
  assert.match(serverSource, /path\.posix\.normalize/)
})
