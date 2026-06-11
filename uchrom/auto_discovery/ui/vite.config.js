import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  define: {
    "process.env.NODE_ENV": JSON.stringify("production")
  },
  resolve: {
    alias: {
      vue: "vue/dist/vue.esm-bundler.js"
    }
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    cssCodeSplit: false,
    minify: true,
    lib: {
      entry: resolve(__dirname, "src/main.js"),
      name: "UChromIdeaGraph",
      formats: ["iife"],
      fileName: () => "idea-graph.iife.js"
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith(".css")) return "style.css";
          return "assets/[name]-[hash][extname]";
        }
      }
    }
  }
});
