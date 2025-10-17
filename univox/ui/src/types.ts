export type RTVIMessage = {
  label?: string
  type: string
  [k: string]: any
}

export type TranscriptionItem = {
  id: string
  text: string
  final: boolean
  ts?: string
}

