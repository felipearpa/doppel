package fixtures.renamed

class Left {
    fun totals(orders: List<Order>): Map<String, Int> {
        val paid = orders.filter { it.status == "paid" }
        val grouped = paid.groupBy { it.customer }
        return grouped.mapValues { entry -> entry.value.sumOf { it.amount } + 10 }
    }
}
