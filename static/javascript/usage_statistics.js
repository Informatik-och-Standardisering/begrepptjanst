const chart_data_element = document.getElementById("views-chart-data");

if (chart_data_element) {
    const chart_data = JSON.parse(chart_data_element.textContent);
    const series = [
        { canvas_id: "views-chart", label: "Visningar", data: chart_data.views, color: "--chart-line" },
        { canvas_id: "visitors-chart", label: "Unika besökare per dag", data: chart_data.visitors, color: "--chart-line-2" },
    ];
    let charts = [];

    function css_variable(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }

    function line_chart(canvas, label, data, color) {
        const text_color = css_variable("--body-quiet-color");

        return new Chart(canvas, {
            type: "line",
            data: {
                labels: chart_data.labels,
                datasets: [{
                    label: label,
                    data: data,
                    borderColor: color,
                    backgroundColor: color,
                    borderWidth: 2,
                    pointRadius: data.length === 1 ? 4 : 0,
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
                        afterFit: (axis) => { axis.width = 48; },
                        beginAtZero: true,
                        grid: { color: css_variable("--hairline-color") },
                        ticks: { color: text_color, precision: 0, maxTicksLimit: 5 },
                    },
                },
            },
        });
    }

    function render_charts() {
        charts.forEach((chart) => chart.destroy());
        charts = series.map((item) => line_chart(
            document.getElementById(item.canvas_id), item.label, item.data, css_variable(item.color)
        ));
    }

    render_charts();
    new MutationObserver(render_charts).observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-theme"],
    });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render_charts);
}

document.querySelectorAll("[data-toggle-rows]").forEach((button) => {
    button.addEventListener("click", () => {
        const extra_rows = document.querySelectorAll(button.dataset.toggleRows);
        const expanding = extra_rows[0].hidden;
        extra_rows.forEach((row) => { row.hidden = !expanding; });
        button.textContent = expanding ? button.dataset.less : button.dataset.more;
    });
});
