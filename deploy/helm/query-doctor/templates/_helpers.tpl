{{/*
Expand the chart name.
*/}}
{{- define "query-doctor.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a fully qualified app name.
*/}}
{{- define "query-doctor.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Chart label.
*/}}
{{- define "query-doctor.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels.
*/}}
{{- define "query-doctor.labels" -}}
helm.sh/chart: {{ include "query-doctor.chart" . }}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/component: web
app.kubernetes.io/part-of: query-doctor
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels must stay stable across pod-template restarts.
*/}}
{{- define "query-doctor.selectorLabels" -}}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: web
{{- end -}}

{{/*
Selector labels for the optional synthetic self-test Job.
*/}}
{{- define "query-doctor.selfTestSelectorLabels" -}}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: self-test
{{- end -}}

{{/*
Labels for the optional synthetic self-test Job.
*/}}
{{- define "query-doctor.selfTestLabels" -}}
helm.sh/chart: {{ include "query-doctor.chart" . }}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/component: self-test
app.kubernetes.io/part-of: query-doctor
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels for the optional Recent summary collector CronJob.
*/}}
{{- define "query-doctor.recentSummaryCollectorSelectorLabels" -}}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: recent-summary-collector
{{- end -}}

{{/*
Labels for the optional Recent summary collector CronJob.
*/}}
{{- define "query-doctor.recentSummaryCollectorLabels" -}}
helm.sh/chart: {{ include "query-doctor.chart" . }}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/component: recent-summary-collector
app.kubernetes.io/part-of: query-doctor
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels for the optional Recent history operator readiness CronJob.
*/}}
{{- define "query-doctor.recentHistoryOperatorReadinessSelectorLabels" -}}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: recent-history-operator-readiness
{{- end -}}

{{/*
Labels for the optional Recent history operator readiness CronJob.
*/}}
{{- define "query-doctor.recentHistoryOperatorReadinessLabels" -}}
helm.sh/chart: {{ include "query-doctor.chart" . }}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/component: recent-history-operator-readiness
app.kubernetes.io/part-of: query-doctor
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels for the optional Recent profile worker CronJob.
*/}}
{{- define "query-doctor.recentProfileWorkerSelectorLabels" -}}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: recent-profile-worker
{{- end -}}

{{/*
Labels for the optional Recent profile worker CronJob.
*/}}
{{- define "query-doctor.recentProfileWorkerLabels" -}}
helm.sh/chart: {{ include "query-doctor.chart" . }}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/component: recent-profile-worker
app.kubernetes.io/part-of: query-doctor
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels for the optional Recent profile remediation CronJob.
*/}}
{{- define "query-doctor.recentProfileRemediationSelectorLabels" -}}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: recent-profile-remediation
{{- end -}}

{{/*
Labels for the optional Recent profile remediation CronJob.
*/}}
{{- define "query-doctor.recentProfileRemediationLabels" -}}
helm.sh/chart: {{ include "query-doctor.chart" . }}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/component: recent-profile-remediation
app.kubernetes.io/part-of: query-doctor
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels for the optional Recent history retention CronJob.
*/}}
{{- define "query-doctor.recentHistoryRetentionSelectorLabels" -}}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: recent-history-retention
{{- end -}}

{{/*
Labels for the optional Recent history retention CronJob.
*/}}
{{- define "query-doctor.recentHistoryRetentionLabels" -}}
helm.sh/chart: {{ include "query-doctor.chart" . }}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/component: recent-history-retention
app.kubernetes.io/part-of: query-doctor
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Service account name.
*/}}
{{- define "query-doctor.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "query-doctor.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Container image reference.
*/}}
{{- define "query-doctor.image" -}}
{{- $repository := required "image.repository is required" .Values.image.repository -}}
{{- if .Values.image.digest -}}
{{- printf "%s@%s" $repository .Values.image.digest -}}
{{- else -}}
{{- printf "%s:%s" $repository (default .Chart.AppVersion .Values.image.tag) -}}
{{- end -}}
{{- end -}}

{{/*
ConfigMap name.
*/}}
{{- define "query-doctor.configMapName" -}}
{{- if .Values.config.existingConfigMap -}}
{{- .Values.config.existingConfigMap -}}
{{- else if .Values.config.name -}}
{{- .Values.config.name -}}
{{- else -}}
{{- printf "%s-config" (include "query-doctor.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
PersistentVolumeClaim name.
*/}}
{{- define "query-doctor.claimName" -}}
{{- if .Values.persistence.existingClaim -}}
{{- .Values.persistence.existingClaim -}}
{{- else -}}
{{- printf "%s-cases" (include "query-doctor.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Optional CNPG Cluster name for Recent history Postgres.
*/}}
{{- define "query-doctor.recentHistoryCnpgClusterName" -}}
{{- $recentHistory := .Values.recentHistory | default dict -}}
{{- $postgres := (get $recentHistory "postgres") | default dict -}}
{{- $cnpg := (get $postgres "cnpg") | default dict -}}
{{- if (get $cnpg "name") -}}
{{- get $cnpg "name" | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-history" (include "query-doctor.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Labels for optional Recent history Postgres storage objects.
*/}}
{{- define "query-doctor.recentHistoryPostgresLabels" -}}
helm.sh/chart: {{ include "query-doctor.chart" . }}
app.kubernetes.io/name: {{ include "query-doctor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/component: recent-history-postgres
app.kubernetes.io/part-of: query-doctor
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
