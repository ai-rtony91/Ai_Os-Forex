import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { cpSync, existsSync, readFileSync, writeFileSync } from 'node:fs'
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
  'package-lock.json',
  'server.js',
  'server',
  'THIRD_PARTY_ATTRIBUTIONS.md',
]

function readJsonFile(filePath) {
  return JSON.parse(readFileSync(filePath, 'utf8'))
}

function createDeploymentPackageJson(rootDir) {
  const sourcePackage = readJsonFile(path.resolve(rootDir, 'package.json'))
  return {
    name: sourcePackage.name,
    private: true,
    version: sourcePackage.version,
    type: sourcePackage.type,
    scripts: {
      start: 'node server.js',
    },
    dependencies: {
      jose: sourcePackage.dependencies.jose,
    },
    overrides: sourcePackage.overrides,
  }
}

function autonomyBridgeStateLoader() {
  let rootDir = process.cwd()

  return {
    name: 'aios-autonomy-bridge-state-loader',
    configResolved(config) {
      rootDir = config.root
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

      const samplePath = path.resolve(
        rootDir,
        'mock-data/autonomy_bridge_state.sample.json',
      )

      this.addWatchFile(samplePath)

      const payload = {
        sourceLabel: 'sample',
        sourcePath: 'mock-data/autonomy_bridge_state.sample.json',
        fallbackReason: 'Build-time browser bundle uses sample data only. Live runtime data is read through authenticated server routes.',
        data: readJsonFile(samplePath),
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

      writeFileSync(
        path.join(outDir, 'package.json'),
        `${JSON.stringify(createDeploymentPackageJson(rootDir), null, 2)}\n`,
      )
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
