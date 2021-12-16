import taichi as ti
import pandas as pd
import numpy as np
import fire


from .io import read_particles


def praticles_df_to_fields(df):
    pos = ti.Vector.field(3, ti.f32, shape=df.shape[0])
    pos.from_numpy(df[['x', 'y', 'z']].values.astype(np.float32))
    color = ti.Vector.field(3, ti.f32, shape=df.shape[0])
    if 'color' not in df:
        chroms = df['chrom'].unique()
        chr2color = pd.DataFrame({
            "chrom": chroms,
            "r": np.random.rand(chroms.shape[0]),
            "g": np.random.rand(chroms.shape[0]),
            "b": np.random.rand(chroms.shape[0]),
        })
        chr2color.index = chr2color['chrom']
        color.from_numpy(chr2color.loc[df['chrom']][['r', 'g', 'b']].values.astype(np.float32))
    else:
        clist = list(df['color'])
        color_rgb = clist.map(lambda h: tuple(int(h[i+1:i+2+1], 16)/255 for i in (0, 2, 4)))
        color.from_numpy(np.array(list(color_rgb)))
    return pos, color


@ti.kernel
def set_indices(indices: ti.template(), num_edge: ti.i32):
    for i in range(num_edge):
        indices[i*3] = i
        indices[i*3+1] = i
        indices[i*3+2] = i + 1


def show_in_gui(df):
    window = ti.ui.Window("particles", (512, 512))
    canvas = window.get_canvas()
    scene = ti.ui.Scene()
    camera = ti.ui.make_camera()
    camera.position(10, 10, 10)
    camera.lookat(0, 0, 0)
    camera.fov(55)
    pos, color = praticles_df_to_fields(df)

    num_edge = df.shape[0] - df['chrom'].unique().shape[0]
    indices = ti.field(int, num_edge*3)
    set_indices(indices, num_edge)

    def render():
        camera.track_user_inputs(window, movement_speed=0.1, hold_key=ti.ui.LMB)
        scene.set_camera(camera)
        scene.ambient_light((1.0, 1.0, 1.0))
        scene.point_light(pos=(10, 10, 10), color=(0.5, 0.5, 0.5))
        scene.particles(pos, radius=0.5, per_vertex_color=color)
        #scene.mesh(pos, indices, per_vertex_color=color)
        canvas.scene(scene)

    while window.running:
        render()
        window.show()


def read_and_draw(path, arch="vulkan"):
    df = read_particles(path)
    ti.init(arch=getattr(ti, arch))
    show_in_gui(df)


if __name__ == "__main__":
    fire.Fire(read_and_draw)
