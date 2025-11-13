{{/*
Expand the name of the chart.
*/}}
{{- define "trading-system.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "trading-system.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "trading-system.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "trading-system.labels" -}}
helm.sh/chart: {{ include "trading-system.chart" . }}
{{ include "trading-system.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "trading-system.selectorLabels" -}}
app.kubernetes.io/name: {{ include "trading-system.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "trading-system.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "trading-system.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image pull secret name
*/}}
{{- define "trading-system.imagePullSecretName" -}}
{{- printf "%s-registry" (include "trading-system.fullname" .) }}
{{- end }}

{{/*
Common environment variables for all services
*/}}
{{- define "trading-system.commonEnv" -}}
- name: GCP_PROJECT_ID
  value: {{ .Values.global.projectId }}
- name: CACHE_BACKEND
  value: "redis"
- name: REDIS_URL
  value: "redis://{{ include "trading-system.fullname" . }}-redis-master.trading.svc.cluster.local:6379"
- name: DISABLE_RATE_LIMITER
  value: {{ .Values.trading.disableRateLimiter | default false | quote }}
{{- end }}
