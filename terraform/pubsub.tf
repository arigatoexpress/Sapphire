resource "google_pubsub_topic" "decisions" {
  name = "decisions"
}

resource "google_pubsub_topic" "positions" {
  name = "positions"
}

resource "google_pubsub_topic" "reasoning" {
  name = "reasoning"
}
