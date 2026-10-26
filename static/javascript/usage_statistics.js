const chart_data_element = document.getElementById("views-chart-data");

if (chart_data_element) {
    const chart_data = JSON.parse(chart_data_element.textContent);
    const canvas = document.getElementById("views-chart");
    let chart = null;

    function css_variable(name) {
        return getComputedStyle(canvas).getPropertyValue(name).trim();
    }

    function render_chart() {
        if (chart) {
            chart.destroy();
        }
        const line_color = css_variable("--chart-line");
        const text_color = css_variable("--body-quiet-color");

        chart = new Chart(canvas, {
            type: "line",
            data: {
                labels: chart_data.labels,
                datasets: [{
                    label: "Visningar",
                    data: chart_data.views,
                    borderColor: line_color,
                    backgroundColor: line_color,
                    borderWidth: 2,
                    pointRadius: chart_data.views.length === 1 ? 4 : 0,
                    pointHoverRadius: 5,
                }],
            },
            options: {
                maintainAspectRatio: false,
                animation: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: { title: (items) => chart_data.titles[items[0].dataIndex] },
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: text_color, maxTicksLimit: 10, maxRotation: 0 },
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: css_variable("--hairline-color") },
                        ticks: { color: text_color, precision: 0 },
                    },
                },
            },
        });
    }

    render_chart();
    new MutationObserver(render_chart).observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-theme"],
    });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render_chart);
}
