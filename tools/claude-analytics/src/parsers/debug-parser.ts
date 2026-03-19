import { createReadStream } from "node:fs";
import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";
import { createInterface } from "node:readline";

export interface DebugEntry {
  timestamp: string;
  level: "DEBUG" | "ERROR" | "WARN" | "INFO";
  context: string;
  message: string;
}

export interface DebugSummary {
  totalFiles: number;
  totalEntries: number;
  errorCount: number;
  warnCount: number;
  recentErrors: DebugEntry[];
  entriesByLevel: Record<string, number>;
}

const LOG_PATTERN = /^(\d{4}-\d{2}-\d{2}T[\d:.]+Z)\s+\[(\w+)]\s+(?:\[([^\]]+)]\s+)?(.*)$/;

export async function parseDebugFile(filePath: string, maxLines = 500): Promise<DebugEntry[]> {
  const entries: DebugEntry[] = [];
  const fileStream = createReadStream(filePath, { encoding: "utf-8" });
  const rl = createInterface({ input: fileStream, crlfDelay: Infinity });
  let count = 0;

  for await (const line of rl) {
    if (count >= maxLines) break;
    const match = line.match(LOG_PATTERN);
    if (match) {
      entries.push({
        timestamp: match[1],
        level: match[2] as DebugEntry["level"],
        context: match[3] ?? "",
        message: match[4],
      });
      count++;
    }
  }
  return entries;
}

export async function getDebugSummary(claudeDataDir: string, recentCount = 20): Promise<DebugSummary> {
  const debugDir = join(claudeDataDir, "debug");
  let totalFiles = 0;
  let totalEntries = 0;
  let errorCount = 0;
  let warnCount = 0;
  const entriesByLevel: Record<string, number> = {};
  const allErrors: DebugEntry[] = [];

  try {
    const files = await readdir(debugDir);
    totalFiles = files.filter((f) => f.endsWith(".txt")).length;

    // Sort files by modification time (most recent first)
    const fileStats = await Promise.all(
      files
        .filter((f) => f.endsWith(".txt"))
        .map(async (f) => {
          const path = join(debugDir, f);
          const s = await stat(path);
          return { path, mtime: s.mtime.getTime() };
        })
    );
    fileStats.sort((a, b) => b.mtime - a.mtime);

    // Parse the 10 most recent debug files
    const recentFiles = fileStats.slice(0, 10);
    for (const { path } of recentFiles) {
      const entries = await parseDebugFile(path);
      totalEntries += entries.length;

      for (const entry of entries) {
        entriesByLevel[entry.level] = (entriesByLevel[entry.level] ?? 0) + 1;
        if (entry.level === "ERROR") {
          errorCount++;
          allErrors.push(entry);
        }
        if (entry.level === "WARN") warnCount++;
      }
    }
  } catch {
    // Debug dir may not exist
  }

  // Sort errors by timestamp descending and take the most recent
  allErrors.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  const recentErrors = allErrors.slice(0, recentCount);

  return {
    totalFiles,
    totalEntries,
    errorCount,
    warnCount,
    recentErrors,
    entriesByLevel,
  };
}
