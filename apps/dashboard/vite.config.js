import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { cpSync, existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const autonomyBridgeStateModuleId = 'virtual:aios-autonomy-bridge-state'
const resolvedAutonomyBridgeStateModuleId = `\0${autonomyBridgeStateModuleId}`

const staticDashboardOutputs = [
  'AIOS_STATIC_PREVIEW.html',
  'manifest.webmanifest',
  'css',
  'js',
  'icons',
  'assets',
  'mock-data',
  'package.json',
  'server.js',
  'server',
  'THIRD_PARTY_ATTRIBUTIONS.md',
]

function readJsonFile(filePath) {
  return JSON.parse(readFileSync(filePath, 'utf8'))
}

function autonomyBridgeStateLoader() {
  let rootDir = process.cwd()
  let repoRootDir = path.resolve(rootDir, '..', '..')

  return {
    name: 'aios-autonomy-bridge-state-loader',
    configResolved(config) {
      rootDir = config.root
      repoRootDir = path.resolve(rootDir, '..', '..')
    },
    resolveId(id) {
      if (id === autonomyBridgeStateModuleId) {
        return resolvedAutonomyBridgeStateModuleId
      }

      return null
    },
    load(id) {
      if (id !== resolvedAutonomyBridgeStateModuleId) {
        return null
      }

      const configuredLivePath = process.env.AIOS_AUTONOMY_BRIDGE_STATE_PATH
      const livePath = configuredLivePath
        ? path.resolve(repoRootDir, configuredLivePath)
        : path.resolve(
            repoRootDir,
            'telemetry/night_supervisor/AUTONOMY_BRIDGE_STATE.json',
          )
      const samplePath = path.resolve(
        rootDir,
        'mock-data/autonomy_bridge_state.sample.json',
      )

      this.addWatchFile(livePath)
      this.addWatchFile(samplePath)

      let payload

      try {
        payload = {
          sourceLabel: 'LIVE',
          sourcePath: path.relative(repoRootDir, livePath).replaceAll('\\', '/'),
          fallbackReason: null,
          data: readJsonFile(livePath),
        }
      } catch (error) {
        payload = {
          sourceLabel: 'sample',
          sourcePath: path.relative(repoRootDir, samplePath).replaceAll('\\', '/'),
          fallbackReason: error?.message ?? 'Live autonomy bridge state unavailable.',
          data: readJsonFile(samplePath),
        }
      }

      return `export const autonomyBridgeStatePayload = ${JSON.stringify(payload)};`
    },
  }
}

function copyStaticDashboardRuntime() {
  let rootDir = process.cwd()
  let outDir = 'dist'

  return {
    name: 'copy-static-dashboard-runtime',
    apply: 'build',
    configResolved(config) {
      rootDir = config.root
      outDir = path.resolve(config.root, config.build.outDir)
    },
    writeBundle() {
      const missingSources = staticDashboardOutputs.filter((entry) => {
        return !existsSync(path.resolve(rootDir, entry))
      })

      if (missingSources.length > 0) {
        throw new Error(
          `Static dashboard source missing: ${missingSources.join(', ')}`,
        )
      }

      for (const entry of staticDashboardOutputs) {
        cpSync(path.resolve(rootDir, entry), path.join(outDir, entry), {
          recursive: true,
          force: true,
        })
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), autonomyBridgeStateLoader(), copyStaticDashboardRuntime()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8080',
    },
  },
})
