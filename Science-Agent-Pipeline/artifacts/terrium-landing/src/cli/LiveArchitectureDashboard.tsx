/**
 * Live Architecture Dashboard
 * Real-time visualization of the 5-stage science agent pipeline
 * Shows domain routing, parameter resolution, and simulation execution
 */

import React, { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  CheckCircle,
  AlertCircle,
  Clock,
  Zap,
  Database,
  GitBranch,
  BarChart3,
} from "lucide-react";

// Type definitions matching the backend
interface StageMetrics {
  name: string;
  successCount: number;
  failureCount: number;
  avgDurationMs: number;
}

interface DomainStats {
  domain: string;
  count: number;
  avgResolutionMs: number;
  parameterSuccessRate: number; // percentage
}

interface PipelineSnapshot {
  timestamp: Date;
  activeJobs: number;
  completedJobs: number;
  failedJobs: number;
  avgLatencyMs: number;
  stageMetrics: StageMetrics[];
  domainDistribution: DomainStats[];
  llmSuccessRate: number; // percentage
  literatureHitRate: number; // percentage
}

const DOMAINS = [
  "mm",
  "mm_competitive_inhibition",
  "sir",
  "seir",
  "pcr",
  "monte_carlo_pi",
  "wright_fisher",
  "two_locus_wright_fisher",
  "molecular_dynamics",
  "gillespie_ssa",
  "gillespie_ssa_bimolecular",
  "gillespie_ssa_replicates",
];

const DOMAIN_COLORS: Record<string, string> = {
  mm: "#3b82f6",
  mm_competitive_inhibition: "#f59e0b",
  sir: "#ef4444",
  seir: "#d946ef",
  pcr: "#06b6d4",
  monte_carlo_pi: "#8b5cf6",
  wright_fisher: "#6366f1",
  two_locus_wright_fisher: "#84cc16",
  molecular_dynamics: "#14b8a6",
  gillespie_ssa: "#fb923c",
  gillespie_ssa_bimolecular: "#f43f5e",
  gillespie_ssa_replicates: "#ec4899",
};

const STAGES = [
  "Entity Extraction",
  "Parameter Resolution",
  "Domain Classification",
  "Validation",
  "Simulation Output",
];

const generateMockSnapshot = (): PipelineSnapshot => {
  const now = new Date();
  const stageMetrics: StageMetrics[] = STAGES.map((stage, idx) => ({
    name: stage,
    successCount: Math.floor(Math.random() * 100) + 50,
    failureCount: Math.floor(Math.random() * 10),
    avgDurationMs: 50 + Math.random() * 150,
  }));

  const domainDistribution: DomainStats[] = DOMAINS.map((domain) => ({
    domain,
    count: Math.floor(Math.random() * 30) + 5,
    avgResolutionMs: 100 + Math.random() * 400,
    parameterSuccessRate: 85 + Math.random() * 15,
  }));

  return {
    timestamp: now,
    activeJobs: Math.floor(Math.random() * 15),
    completedJobs: Math.floor(Math.random() * 500) + 100,
    failedJobs: Math.floor(Math.random() * 20),
    avgLatencyMs: 200 + Math.random() * 300,
    stageMetrics,
    domainDistribution,
    llmSuccessRate: 92 + Math.random() * 8,
    literatureHitRate: 78 + Math.random() * 15,
  };
};

export function LiveArchitectureDashboard() {
  const [snapshot, setSnapshot] = useState<PipelineSnapshot>(
    generateMockSnapshot(),
  );
  const [history, setHistory] = useState<
    Array<{ time: string; latency: number }>
  >([]);
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);

  // Simulate live updates
  useEffect(() => {
    const interval = setInterval(() => {
      const newSnapshot = generateMockSnapshot();
      setSnapshot(newSnapshot);

      setHistory((prev) => [
        ...prev.slice(-29),
        {
          time: new Date().toLocaleTimeString(),
          latency: Math.round(newSnapshot.avgLatencyMs),
        },
      ]);
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  const successRate = (
    (snapshot.completedJobs /
      (snapshot.completedJobs + snapshot.failedJobs)) *
    100
  ).toFixed(1);

  const topDomains = [...snapshot.domainDistribution]
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);

  return (
    <div className="w-full bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6 rounded-lg space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-white flex items-center gap-2">
          <Zap className="w-8 h-8 text-blue-400" />
          Live Architecture Dashboard
        </h1>
        <p className="text-slate-300">
          Real-time monitoring of the 5-stage science agent pipeline
        </p>
      </div>

      {/* Key Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="bg-slate-700 border-slate-600">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-300 uppercase">Active Jobs</p>
                <p className="text-2xl font-bold text-white">
                  {snapshot.activeJobs}
                </p>
              </div>
              <Clock className="w-8 h-8 text-blue-400" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-700 border-slate-600">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-300 uppercase">Success Rate</p>
                <p className="text-2xl font-bold text-green-400">
                  {successRate}%
                </p>
              </div>
              <CheckCircle className="w-8 h-8 text-green-400" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-700 border-slate-600">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-300 uppercase">
                  Avg Latency
                </p>
                <p className="text-2xl font-bold text-purple-400">
                  {Math.round(snapshot.avgLatencyMs)}ms
                </p>
              </div>
              <BarChart3 className="w-8 h-8 text-purple-400" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-700 border-slate-600">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-300 uppercase">LLM Hit Rate</p>
                <p className="text-2xl font-bold text-orange-400">
                  {Math.round(snapshot.llmSuccessRate)}%
                </p>
              </div>
              <Zap className="w-8 h-8 text-orange-400" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Dashboard */}
      <Tabs defaultValue="latency" className="w-full">
        <TabsList className="grid w-full grid-cols-4 bg-slate-700">
          <TabsTrigger value="latency">Latency</TabsTrigger>
          <TabsTrigger value="stages">Stages</TabsTrigger>
          <TabsTrigger value="domains">Domains</TabsTrigger>
          <TabsTrigger value="resolution">Resolution</TabsTrigger>
        </TabsList>

        {/* Latency Timeline */}
        <TabsContent value="latency" className="space-y-4">
          <Card className="bg-slate-700 border-slate-600">
            <CardHeader>
              <CardTitle className="text-white flex items-center gap-2">
                <Clock className="w-5 h-5" />
                Latency Timeline (Last 30 seconds)
              </CardTitle>
            </CardHeader>
            <CardContent>
              {history.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={history}>
                    <CartesianGrid stroke="#404854" />
                    <XAxis
                      dataKey="time"
                      stroke="#94a3b8"
                      style={{ fontSize: "0.75rem" }}
                    />
                    <YAxis stroke="#94a3b8" />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#1e293b",
                        border: "1px solid #475569",
                      }}
                      labelStyle={{ color: "#e2e8f0" }}
                    />
                    <Line
                      type="monotone"
                      dataKey="latency"
                      stroke="#3b82f6"
                      dot={false}
                      name="Latency (ms)"
                      strokeWidth={2}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-slate-400 text-center py-12">
                  Collecting data...
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Stage Performance */}
        <TabsContent value="stages" className="space-y-4">
          <Card className="bg-slate-700 border-slate-600">
            <CardHeader>
              <CardTitle className="text-white flex items-center gap-2">
                <GitBranch className="w-5 h-5" />
                Pipeline Stage Metrics
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={snapshot.stageMetrics}>
                  <CartesianGrid stroke="#404854" />
                  <XAxis
                    dataKey="name"
                    stroke="#94a3b8"
                    style={{ fontSize: "0.75rem" }}
                  />
                  <YAxis stroke="#94a3b8" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#1e293b",
                      border: "1px solid #475569",
                    }}
                    labelStyle={{ color: "#e2e8f0" }}
                  />
                  <Legend wrapperStyle={{ color: "#cbd5e1" }} />
                  <Bar dataKey="successCount" fill="#10b981" name="Success" />
                  <Bar dataKey="failureCount" fill="#ef4444" name="Failure" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Domain Distribution */}
        <TabsContent value="domains" className="space-y-4">
          <Card className="bg-slate-700 border-slate-600">
            <CardHeader>
              <CardTitle className="text-white flex items-center gap-2">
                <Database className="w-5 h-5" />
                Domain Distribution (Top 5)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={topDomains}
                    dataKey="count"
                    nameKey="domain"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={({ domain, count }) => `${domain}: ${count}`}
                  >
                    {topDomains.map((entry) => (
                      <Cell
                        key={entry.domain}
                        fill={DOMAIN_COLORS[entry.domain] || "#64748b"}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#1e293b",
                      border: "1px solid #475569",
                    }}
                    labelStyle={{ color: "#e2e8f0" }}
                  />
                </PieChart>
              </ResponsiveContainer>

              {/* Domain Legend */}
              <div className="grid grid-cols-2 gap-2 pt-4 border-t border-slate-600">
                {topDomains.map((d) => (
                  <div
                    key={d.domain}
                    className="flex items-center gap-2 text-sm cursor-pointer hover:bg-slate-600 p-2 rounded"
                    onClick={() =>
                      setSelectedDomain(
                        selectedDomain === d.domain ? null : d.domain,
                      )
                    }
                  >
                    <div
                      className="w-3 h-3 rounded"
                      style={{
                        backgroundColor:
                          DOMAIN_COLORS[d.domain] || "#64748b",
                      }}
                    />
                    <span className="text-slate-200">{d.domain}</span>
                    <Badge variant="secondary" className="ml-auto text-xs">
                      {d.count}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {selectedDomain && (
            <Card className="bg-slate-700 border-slate-600">
              <CardHeader>
                <CardTitle className="text-white text-base">
                  {selectedDomain} Details
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {snapshot.domainDistribution
                  .filter((d) => d.domain === selectedDomain)
                  .map((d) => (
                    <div key={d.domain} className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-300">Total Runs:</span>
                        <span className="text-white font-mono">{d.count}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-300">Avg Resolution:</span>
                        <span className="text-white font-mono">
                          {Math.round(d.avgResolutionMs)}ms
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-slate-300">Success Rate:</span>
                        <span className="text-white font-mono">
                          {Math.round(d.parameterSuccessRate)}%
                        </span>
                      </div>
                    </div>
                  ))}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Resolution Metrics */}
        <TabsContent value="resolution" className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Card className="bg-slate-700 border-slate-600">
              <CardHeader>
                <CardTitle className="text-white text-sm">
                  LLM Success Rate
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-orange-400">
                  {Math.round(snapshot.llmSuccessRate)}%
                </div>
                <p className="text-xs text-slate-400 mt-2">
                  LLM domain classification accuracy
                </p>
              </CardContent>
            </Card>

            <Card className="bg-slate-700 border-slate-600">
              <CardHeader>
                <CardTitle className="text-white text-sm">
                  Literature Hit Rate
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-green-400">
                  {Math.round(snapshot.literatureHitRate)}%
                </div>
                <p className="text-xs text-slate-400 mt-2">
                  BRENDA/PubMed parameter resolution
                </p>
              </CardContent>
            </Card>
          </div>

          <Alert className="bg-blue-900/30 border-blue-700">
            <AlertCircle className="h-4 w-4 text-blue-400" />
            <AlertDescription className="text-blue-200">
              <strong>Pipeline Health:</strong> System operating at{" "}
              <span className="font-bold">{successRate}%</span> success rate
              with average latency of{" "}
              <span className="font-bold">{Math.round(snapshot.avgLatencyMs)}ms</span>.
              All stages validated.
            </AlertDescription>
          </Alert>

          <Card className="bg-slate-700 border-slate-600">
            <CardHeader>
              <CardTitle className="text-white text-base">
                5-Stage Pipeline Summary
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {STAGES.map((stage, idx) => {
                const metric = snapshot.stageMetrics[idx];
                const successRate = (
                  (metric.successCount /
                    (metric.successCount + metric.failureCount)) *
                  100
                ).toFixed(0);

                return (
                  <div key={stage} className="space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-slate-300">
                        {idx + 1}. {stage}
                      </span>
                      <Badge
                        variant={parseInt(successRate) > 95 ? "default" : "secondary"}
                        className="text-xs"
                      >
                        {successRate}% OK
                      </Badge>
                    </div>
                    <div className="w-full bg-slate-600 rounded-full h-2">
                      <div
                        className="bg-blue-500 h-2 rounded-full transition-all"
                        style={{ width: `${successRate}%` }}
                      />
                    </div>
                    <p className="text-xs text-slate-400">
                      {metric.successCount} ✓ · {metric.failureCount} ✗ ·{" "}
                      {Math.round(metric.avgDurationMs)}ms avg
                    </p>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Architecture Overview */}
      <Card className="bg-slate-700 border-slate-600">
        <CardHeader>
          <CardTitle className="text-white">Architecture Components</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-blue-300">Frontend</h4>
              <p className="text-xs text-slate-300">
                React dashboard with live metrics, domain routing visualization,
                and stage performance monitoring
              </p>
            </div>
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-green-300">Backend</h4>
              <p className="text-xs text-slate-300">
                Express server with TypeScript, PostgreSQL queue, LLM routing
                via Groq/OpenRouter, and multi-provider failover
              </p>
            </div>
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-yellow-300">
                Science Agent
              </h4>
              <p className="text-xs text-slate-300">
                Python bridge for entity extraction, literature resolution
                (BRENDA/PubMed), and provenance tracking
              </p>
            </div>
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-purple-300">Simulators</h4>
              <p className="text-xs text-slate-300">
                Terium engine dispatch for 13 domain types: MM kinetics,
                competitive inhibition, epidemiology, population genetics, etc.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default LiveArchitectureDashboard;
