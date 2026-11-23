package fixtures.renamed

class Right {
    fun sums(rows: List<Invoice>): Map<String, Int> {
        val settled = rows.filter { it.state == "settled" }
        val byClient = settled.groupBy { it.client }
        return byClient.mapValues { pair -> pair.value.sumOf { it.total } + 99 }
    }
}
