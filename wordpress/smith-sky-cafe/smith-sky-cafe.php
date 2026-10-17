<?php
/**
 * Plugin Name: Smith & Sky Cafe Dashboard
 * Description: Elementor-friendly shortcodes for the Smith & Sky cafe inventory Flask API.
 * Version: 0.1.0
 * Author: Smith & Sky
 */

if (!defined('ABSPATH')) {
    exit;
}

define('SSC_PLUGIN_URL', plugin_dir_url(__FILE__));
define('SSC_PLUGIN_PATH', plugin_dir_path(__FILE__));

function ssc_register_settings() {
    register_setting('ssc_settings', 'ssc_api_base_url', [
        'type' => 'string',
        'sanitize_callback' => 'esc_url_raw',
        'default' => 'https://api.example.com',
    ]);
}
add_action('admin_init', 'ssc_register_settings');

function ssc_register_settings_page() {
    add_options_page(
        'Smith & Sky Cafe',
        'Smith & Sky Cafe',
        'manage_options',
        'ssc-settings',
        'ssc_render_settings_page'
    );
}
add_action('admin_menu', 'ssc_register_settings_page');

function ssc_render_settings_page() {
    ?>
    <div class="wrap">
        <h1>Smith & Sky Cafe</h1>
        <form method="post" action="options.php">
            <?php settings_fields('ssc_settings'); ?>
            <table class="form-table" role="presentation">
                <tr>
                    <th scope="row"><label for="ssc_api_base_url">Flask API base URL</label></th>
                    <td>
                        <input name="ssc_api_base_url" id="ssc_api_base_url" type="url" class="regular-text"
                               value="<?php echo esc_attr(get_option('ssc_api_base_url', 'https://api.example.com')); ?>">
                        <p class="description">Example: https://dashboard-api.smithandsky.com</p>
                    </td>
                </tr>
            </table>
            <?php submit_button(); ?>
        </form>
    </div>
    <?php
}

function ssc_enqueue_assets() {
    wp_enqueue_style('ssc-cafe', SSC_PLUGIN_URL . 'assets/cafe-dashboard.css', [], '0.1.0');
    wp_enqueue_script('ssc-cafe', SSC_PLUGIN_URL . 'assets/cafe-dashboard.js', [], '0.1.0', true);
    wp_localize_script('ssc-cafe', 'SmithSkyCafe', [
        'apiBaseUrl' => untrailingslashit(get_option('ssc_api_base_url', 'https://api.example.com')),
        'loginUrl' => home_url('/cafe-login/'),
        'adminUrl' => home_url('/cafe-admin/'),
        'portalUrl' => home_url('/cafe-portal/'),
    ]);
}
add_action('wp_enqueue_scripts', 'ssc_enqueue_assets');

function ssc_shell($view) {
    return '<div class="ssc-app" data-ssc-view="' . esc_attr($view) . '">'
        . '<div class="ssc-loading">Loading Smith &amp; Sky...</div>'
        . '</div>';
}

function ssc_login_shortcode() {
    return ssc_shell('login');
}

function ssc_admin_shortcode() {
    return ssc_shell('admin');
}

function ssc_deliveries_shortcode() {
    return ssc_shell('deliveries');
}

function ssc_cafes_shortcode() {
    return ssc_shell('cafes');
}

function ssc_reports_shortcode() {
    return ssc_shell('reports');
}

function ssc_portal_shortcode() {
    return ssc_shell('portal');
}

function ssc_new_sale_shortcode() {
    return ssc_shell('new-sale');
}

function ssc_history_shortcode() {
    return ssc_shell('history');
}

add_shortcode('smith_sky_cafe_login', 'ssc_login_shortcode');
add_shortcode('smith_sky_cafe_admin', 'ssc_admin_shortcode');
add_shortcode('smith_sky_cafe_deliveries', 'ssc_deliveries_shortcode');
add_shortcode('smith_sky_cafe_cafes', 'ssc_cafes_shortcode');
add_shortcode('smith_sky_cafe_reports', 'ssc_reports_shortcode');
add_shortcode('smith_sky_cafe_portal', 'ssc_portal_shortcode');
add_shortcode('smith_sky_cafe_new_sale', 'ssc_new_sale_shortcode');
add_shortcode('smith_sky_cafe_history', 'ssc_history_shortcode');
