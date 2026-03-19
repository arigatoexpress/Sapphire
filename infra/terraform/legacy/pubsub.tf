resource "google_pubsub_topic" "decisions" {
  name = "decisions"
}

resource "google_pubsub_topic" "positions" {
  name = "positions"
}

resource "google_pubsub_topic" "reasoning" {
  name = "reasoning"
}

resource "google_pubsub_topic" "sapphire-vpin-tick-data" {
  name = "sapphire-vpin-tick-data"
}

resource "google_pubsub_topic" "sapphire-vpin-positions" {
  name = "sapphire-vpin-positions"
}
