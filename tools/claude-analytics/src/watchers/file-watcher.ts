import chokidar from "chokidar";
import { EventEmitter } from "node:events";

export interface FileChangeEvent {
  type: "add" | "change" | "unlink";
  path: string;
  timestamp: string;
  category: "stats" | "session" | "debug" | "subagent" | "other";
}

function categorize(filePath: string): FileChangeEvent["category"] {
  if (filePath.includes("stats-cache.json")) return "stats";
  if (filePath.includes("debug/")) return "debug";
  if (filePath.includes("subagents/")) return "subagent";
  if (filePath.endsWith(".jsonl")) return "session";
  return "other";
}

export class ClaudeFileWatcher extends EventEmitter {
  private watcher: chokidar.FSWatcher | null = null;
  private claudeDataDir: string;

  constructor(claudeDataDir: string) {
    super();
    this.claudeDataDir = claudeDataDir;
  }

  start(): void {
    const watchPaths = [
      `${this.claudeDataDir}/stats-cache.json`,
      `${this.claudeDataDir}/history.jsonl`,
      `${this.claudeDataDir}/projects/**/*.jsonl`,
      `${this.claudeDataDir}/debug/**/*.txt`,
    ];

    this.watcher = chokidar.watch(watchPaths, {
      persistent: true,
      ignoreInitial: true,
      awaitWriteFinish: {
        stabilityThreshold: 300,
        pollInterval: 100,
      },
    });

    this.watcher
      .on("add", (path) => this.handleEvent("add", path))
      .on("change", (path) => this.handleEvent("change", path))
      .on("unlink", (path) => this.handleEvent("unlink", path));
  }

  private handleEvent(type: FileChangeEvent["type"], path: string): void {
    const event: FileChangeEvent = {
      type,
      path,
      timestamp: new Date().toISOString(),
      category: categorize(path),
    };
    this.emit("change", event);
  }

  async stop(): Promise<void> {
    if (this.watcher) {
      await this.watcher.close();
      this.watcher = null;
    }
  }
}
