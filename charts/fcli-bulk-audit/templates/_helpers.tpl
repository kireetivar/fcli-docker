{{- define "bulk.name" -}}
{{- printf "%s-bulk-audit" .Release.Name | trunc 52 | trimSuffix "-" -}}
{{- end -}}
{{- define "bulk.labels" -}}
app.kubernetes.io/name: fcli-bulk-audit
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}
{{- define "bulk.image" -}}
{{- if .Values.image.digest -}}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag -}}
{{- end -}}
{{- end -}}

{{- define "bulk.jobSpec" -}}
backoffLimit: 0
activeDeadlineSeconds: {{ .Values.job.activeDeadlineSeconds }}
ttlSecondsAfterFinished: {{ .Values.job.ttlSecondsAfterFinished }}
template:
  metadata:
    labels:
      {{- include "bulk.labels" . | nindent 6 }}
    {{- with .Values.podAnnotations }}
    annotations:
      {{- toYaml . | nindent 6 }}
    {{- end }}
  spec:
    restartPolicy: Never
    automountServiceAccountToken: false
    terminationGracePeriodSeconds: {{ .Values.job.terminationGracePeriodSeconds }}
    securityContext:
      runAsNonRoot: true
      runAsUser: 10001
      runAsGroup: 10001
      fsGroup: 10001
      seccompProfile:
        type: RuntimeDefault
    {{- with .Values.imagePullSecrets }}
    imagePullSecrets:
      {{- toYaml . | nindent 6 }}
    {{- end }}
    nodeSelector:
      {{- toYaml .Values.nodeSelector | nindent 6 }}
    containers:
      - name: bulk-audit
        image: {{ include "bulk.image" . | quote }}
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop: [ALL]
        env:
          - name: SSC_URL
            value: {{ .Values.audit.sscUrl | quote }}
          - name: SSC_INSECURE
            value: {{ .Values.audit.sscInsecure | default false | quote }}
          - name: AVIATOR_URL
            value: {{ .Values.audit.aviatorUrl | quote }}
          - name: AVIATOR_TENANT
            value: {{ .Values.audit.aviatorTenant | quote }}
          - name: BULK_AUDIT_ACTION
            value: {{ .Values.audit.action | quote }}
          - name: BULK_AUDIT_DRY_RUN
            value: {{ .Values.audit.dryRun | quote }}
          - name: BULK_AUDIT_MAX_AUDITS
            value: {{ .Values.audit.maxAudits | quote }}
          - name: BULK_AUDIT_FILTER
            value: {{ .Values.audit.filter | default "" | quote }}
          - name: BULK_AUDIT_EXCLUDE_FILTER
            value: {{ .Values.audit.excludeFilter | quote }}
          - name: BULK_AUDIT_TIMEOUT_SECONDS
            value: {{ .Values.audit.timeoutSeconds | quote }}
          {{- if .Values.truststore.existingSecret }}
          - name: FCLI_TRUSTSTORE
            value: /run/truststore/store
          - name: FCLI_TRUSTSTORE_TYPE
            value: {{ .Values.truststore.type | quote }}
          - name: FCLI_TRUSTSTORE_PWD_FILE
            value: /run/truststore/password
          {{- end }}
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
        volumeMounts:
          - name: sessions
            mountPath: /work
          - name: temporary
            mountPath: /tmp
          - name: credentials
            mountPath: /run/secrets
            readOnly: true
          {{- if .Values.truststore.existingSecret }}
          - name: truststore
            mountPath: /run/truststore
            readOnly: true
          {{- end }}
    volumes:
      - name: sessions
        emptyDir:
          medium: Memory
          sizeLimit: {{ .Values.storage.sessionSizeLimit }}
      - name: temporary
        emptyDir:
          medium: Memory
          sizeLimit: {{ .Values.storage.temporarySizeLimit }}
      - name: credentials
        secret:
          secretName: {{ .Values.existingSecret | quote }}
          defaultMode: 0440
          items:
            - key: ssc-token
              path: ssc-token
            - key: aviator-token
              path: aviator-token
            - key: aviator-private-key
              path: aviator-private-key
      {{- if .Values.truststore.existingSecret }}
      - name: truststore
        secret:
          secretName: {{ .Values.truststore.existingSecret | quote }}
          defaultMode: 0440
          items:
            - key: {{ .Values.truststore.key | quote }}
              path: store
            - key: {{ .Values.truststore.passwordKey | quote }}
              path: password
      {{- end }}
{{- end -}}
