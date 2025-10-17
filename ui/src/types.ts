export type RTVIMessage = {
  label?: string
  type: string
  [k: string]: any
}

export type TranscriptItem = {
  id: string
  text: string
  final: boolean
  ts?: string
}
